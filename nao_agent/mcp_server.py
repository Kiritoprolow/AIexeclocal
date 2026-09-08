"""
nao_agent.mcp_server
=====================
Đăng ký các tool (core + space_ops nếu bật) lên 1 server MCP thật (fastmcp).

MẶC ĐỊNH (local-first): transport="stdio" — client MCP (Claude Desktop,
Cursor, VS Code Copilot Chat, Codex CLI, ...) tự spawn tiến trình này và
nói chuyện qua stdin/stdout. KHÔNG cần HTTP, KHÔNG cần curl, KHÔNG cần
token — tiến trình con chạy trên máy của chính người dùng nên đã tin cậy
mặc định. Đây là cách phổ biến và tương thích nhất để "chạy local".

TÙY CHỌN (giữ tương thích ngược, cho ai vẫn muốn deploy remote như bản cũ):
transport="http" — dựng lại đúng kiểu MCP-over-HTTP + REST API trần
('/api/*', gọi được bằng curl) + GitHub OAuth/Bearer token y như trước,
để vẫn host được trên Hugging Face Space hoặc bất kỳ server nào.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastmcp import FastMCP

from . import core
from . import secrets_manager

logger = logging.getLogger("nao_agent.mcp_server")


def _register_core_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="list_files")
    def _list_files(path: str = ".", max_depth: int = 2) -> str:
        """Liệt kê cây thư mục của project (thư mục làm việc hiện tại)."""
        return core.tool_list_files(path, max_depth)

    @mcp.tool(name="read_file")
    def _read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
        """Đọc nội dung file trong project."""
        return core.tool_read_file(path, start_line, end_line)

    @mcp.tool(name="find_function")
    def _find_function(path: str, name: str) -> str:
        """Tìm chính xác source code 1 hàm/class/method bằng AST (Python).
        Dùng 'ClassName.method_name' cho method trong class."""
        return core.tool_find_function(path, name)

    @mcp.tool(name="write_file")
    def _write_file(path: str, content: str) -> str:
        """Tạo file MỚI (path chưa tồn tại). KHÔNG có cách nào ghi đè file
        đã tồn tại bằng tool này — nếu path đã có, dùng edit_file để patch,
        hoặc delete_file rồi write_file lại nếu thực sự cần viết lại cả file."""
        return core.tool_write_file(path, content)

    @mcp.tool(name="edit_file")
    def _edit_file(path: str, old_str: str, new_str: str) -> str:
        """Sửa 1 phần file đã có bằng cách thay old_str -> new_str (phải khớp
        chính xác nội dung hiện tại của file)."""
        return core.tool_edit_file(path, old_str, new_str)

    @mcp.tool(name="delete_file")
    def _delete_file(path: str) -> str:
        """Xóa 1 file trong project."""
        return core.tool_delete_file(path)

    @mcp.tool(name="exec_terminal")
    def _exec_terminal(
        command: str,
        timeout: int = 90,
        env: Optional[dict] = None,
        secrets: Optional[list] = None,
    ) -> str:
        """Chạy 1 lệnh shell trong thư mục làm việc của project, như 1
        người dùng thật (đặt biến môi trường, gọi git/ssh/curl/psql...).
        `env`: biến môi trường chỉ áp dụng cho lệnh này. `secrets`: danh
        sách tên secret đã đăng ký qua register_secret() — giá trị thật
        được bơm vào env của lệnh rồi tự động bị che trong output trả về."""
        return core.tool_exec_terminal(command, timeout, env, secrets)

    @mcp.tool(name="set_env")
    def _set_env(key: str, value: str) -> str:
        """Đặt 1 biến môi trường PERSISTENT (áp dụng cho mọi exec_terminal
        sau này, giống `export KEY=value`). Chỉ dùng cho cấu hình KHÔNG
        nhạy cảm — với token/password thật, dùng register_secret() thay vì
        tool này."""
        return core.tool_set_env(key, value)

    @mcp.tool(name="unset_env")
    def _unset_env(key: str) -> str:
        """Bỏ 1 biến môi trường persistent đã đặt bằng set_env."""
        return core.tool_unset_env(key)

    @mcp.tool(name="list_env")
    def _list_env() -> str:
        """Liệt kê TÊN các biến môi trường persistent đang được đặt."""
        return core.tool_list_env()

    @mcp.tool(name="register_secret")
    def _register_secret(name: str, path: str) -> str:
        """Đăng ký 1 secret theo TÊN, trỏ tới 1 file chứa giá trị thật ở
        BẤT KỲ đâu trên máy bạn (vd '~/.secrets/github_token'). Chỉ lưu
        đường dẫn — không bao giờ đọc/in giá trị ra. Sau đó dùng tên này
        trong tham số `secrets` của exec_terminal."""
        return secrets_manager.tool_register_secret(name, path)

    @mcp.tool(name="list_secrets")
    def _list_secrets() -> str:
        """Liệt kê tên + đường dẫn các secret đã đăng ký (không bao giờ
        hiện giá trị thật)."""
        return secrets_manager.tool_list_secrets()

    @mcp.tool(name="forget_secret")
    def _forget_secret(name: str) -> str:
        """Gỡ đăng ký 1 secret theo tên (không xóa file thật trên đĩa)."""
        return secrets_manager.tool_forget_secret(name)

    @mcp.tool(name="complete_task")
    def _complete_task(summary: str = "Đã hoàn thành nhiệm vụ.", notes: str = "") -> str:
        """Báo hiệu đã hoàn thành nhiệm vụ được giao."""
        return core.tool_complete_task(summary, notes)


def _register_space_tools(mcp: FastMCP) -> None:
    """Chỉ gọi khi HF_SPACE_MODE=1 — thêm các tool điều khiển Hugging Face
    Space từ xa (push/restart/refresh_context) bên cạnh các tool core."""
    from . import space_ops

    @mcp.tool(name="push_to_space")
    def _push_to_space(paths: list) -> str:
        """Đẩy các file đã ghi/sửa/xóa lên Space mục tiêu THẬT (publish)."""
        return space_ops.tool_push_to_space(paths)

    @mcp.tool(name="restart_space")
    def _restart_space() -> str:
        """Khởi động lại Space mục tiêu (thường dùng sau khi push xong bản sửa lỗi)."""
        return space_ops.tool_restart_space()

    @mcp.tool(name="refresh_context")
    def _refresh_context(max_depth: int = 3) -> str:
        """Lấy lại bản chụp cây thư mục mới nhất của Space mục tiêu."""
        return space_ops.tool_refresh_context(max_depth)


def build_mcp_server(with_auth_for_http: bool = False) -> FastMCP:
    """Tạo FastMCP instance + đăng ký tool. `with_auth_for_http` chỉ có ý
    nghĩa khi server này sẽ chạy transport="http" (chế độ legacy/remote):
    bật thì cấu hình GitHub OAuth nếu có biến môi trường tương ứng."""
    auth_provider = None
    if with_auth_for_http:
        github_client_id = os.environ.get("GITHUB_CLIENT_ID", "").strip()
        github_client_secret = os.environ.get("GITHUB_CLIENT_SECRET", "").strip()
        allowed_username = os.environ.get("ALLOWED_GITHUB_USERNAME", "").strip()
        public_base_url = os.environ.get("MCP_PUBLIC_BASE_URL", "").strip()

        if github_client_id and github_client_secret and public_base_url:
            from fastmcp.server.auth.providers.github import GitHubProvider

            auth_provider = GitHubProvider(
                client_id=github_client_id,
                client_secret=github_client_secret,
                base_url=public_base_url,
                required_scopes=["user"],
            )
            if allowed_username:
                original_verify = auth_provider.verify_token

                async def _verify_owner_only(token: str):
                    access = await original_verify(token)
                    if access is None:
                        return None
                    username = (access.claims or {}).get("login")
                    if username != allowed_username:
                        logger.warning(
                            "⛔ Từ chối MCP: tài khoản GitHub '%s' không phải chủ sở hữu ('%s').",
                            username, allowed_username,
                        )
                        return None
                    return access

                auth_provider.verify_token = _verify_owner_only
            else:
                logger.warning(
                    "⚠️ Đã cấu hình GitHub OAuth nhưng CHƯA đặt ALLOWED_GITHUB_USERNAME — "
                    "BẤT KỲ ai có tài khoản GitHub cũng đăng nhập được! Thêm biến này ngay."
                )

    mcp = FastMCP("nao-coding-agent", auth=auth_provider)

    if with_auth_for_http and auth_provider is None:
        # Không có OAuth -> fallback Bearer token tĩnh, fail-closed nếu thiếu.
        from fastmcp.server.middleware import Middleware
        from fastmcp.server.dependencies import get_http_headers
        from fastmcp.exceptions import ToolError

        secret_token = os.environ.get("MCP_SECRET_TOKEN", "").strip()

        class _BearerAuthMiddleware(Middleware):
            async def on_call_tool(self, context, call_next):
                if not secret_token:
                    raise ToolError("MCP server chưa cấu hình MCP_SECRET_TOKEN — từ chối mọi request.")
                headers = get_http_headers()
                auth = headers.get("authorization", "")
                if not auth.startswith("Bearer ") or auth[len("Bearer "):].strip() != secret_token:
                    raise ToolError("Access denied: token sai hoặc thiếu.")
                return await call_next(context)

        mcp.add_middleware(_BearerAuthMiddleware())
        if not secret_token:
            logger.warning(
                "⚠️ Chế độ http nhưng chưa cấu hình MCP_SECRET_TOKEN -> mọi request bị "
                "từ chối (fail-closed). Đặt biến này nếu muốn dùng thật."
            )

    _register_core_tools(mcp)
    if os.environ.get("HF_SPACE_MODE", "").strip() in ("1", "true", "True", "yes"):
        _register_space_tools(mcp)

    return mcp


def run_stdio() -> None:
    """Chế độ CHẠY LOCAL mặc định — client MCP tự spawn tiến trình này."""
    mcp = build_mcp_server(with_auth_for_http=False)
    logger.info("🚀 nao-coding-agent: MCP server chạy qua stdio, WORKDIR=%s", core.WORKDIR)
    mcp.run(transport="stdio")


def run_http(host: str = "127.0.0.1", port: int = 8765, mount_rest_api: bool = True) -> None:
    """Chế độ legacy/remote — MCP-over-HTTP (+ REST '/api/*' gọi bằng curl
    nếu mount_rest_api=True) trên 1 app FastAPI, giống hệt kiến trúc gốc.
    Mặc định bind 127.0.0.1 (chỉ máy này gọi được) — muốn public/host thật
    (vd trên HF Space) thì tự truyền host="0.0.0.0"."""
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import RedirectResponse

    mcp = build_mcp_server(with_auth_for_http=True)
    mcp_asgi_app = mcp.http_app(path="/mcp-server/mcp")

    fastapi_app = FastAPI(lifespan=mcp_asgi_app.lifespan)

    @fastapi_app.get("/", include_in_schema=False)
    def _root():
        return RedirectResponse(url="/mcp-server/mcp")

    if mount_rest_api:
        _mount_rest_api(fastapi_app)

    fastapi_app.mount("/", mcp_asgi_app)
    logger.info("🚀 nao-coding-agent: HTTP server tại %s:%s (WORKDIR=%s)", host, port, core.WORKDIR)
    uvicorn.run(fastapi_app, host=host, port=port)


def _mount_rest_api(fastapi_app) -> None:
    """REST API trần '/api/*' — cho ai thích/cần gọi bằng curl từ bất kỳ
    terminal nào, giữ lại để tương thích ngược, KHÔNG còn là cách bắt buộc."""
    from fastapi import Request
    from fastapi.responses import JSONResponse
    from starlette.exceptions import HTTPException as StarletteHTTPException

    secret_token = os.environ.get("MCP_SECRET_TOKEN", "").strip()
    tool_impls = dict(core.CORE_TOOLS)
    tool_impls.update(secrets_manager.SECRET_TOOLS)
    if os.environ.get("HF_SPACE_MODE", "").strip() in ("1", "true", "True", "yes"):
        from . import space_ops
        tool_impls.update(space_ops.SPACE_TOOLS)

    def _check_auth(request: Request) -> None:
        if not secret_token:
            raise StarletteHTTPException(status_code=503, detail="REST API chưa bật: thiếu MCP_SECRET_TOKEN.")
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[len("Bearer "):].strip() != secret_token:
            raise StarletteHTTPException(status_code=401, detail="Sai hoặc thiếu Bearer token.")

    @fastapi_app.get("/api/tools", include_in_schema=False)
    def _api_list_tools():
        return {
            "tools": sorted(tool_impls.keys()),
            "usage": 'POST /api/call  body: {"tool": "<tên tool>", "args": {...}}  '
                     "header: Authorization: Bearer <MCP_SECRET_TOKEN>",
        }

    @fastapi_app.post("/api/call", include_in_schema=False)
    async def _api_call(request: Request):
        _check_auth(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        name = str(body.get("tool", ""))
        args = body.get("args") or {}
        if not isinstance(args, dict):
            return JSONResponse({"ok": False, "error": "'args' phải là object/dict."}, status_code=400)
        impl = tool_impls.get(name)
        if not impl:
            return JSONResponse({"ok": False, "error": f"Không có tool '{name}'."}, status_code=404)
        try:
            result = impl(**args)
            return {"ok": True, "result": result}
        except core.PipelineToolError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        except TypeError as e:
            return JSONResponse({"ok": False, "error": f"Sai tham số cho '{name}': {e}"}, status_code=400)
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

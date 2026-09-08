"""
nao_agent.core
==============
Toàn bộ tool "sửa code" gốc (list_files/read_file/find_function/write_file/
edit_file/delete_file/exec_terminal) — TÁCH HẲN khỏi mọi thứ đặc thù của
Hugging Face Space (snapshot download, push_to_space, ZeroGPU, Telegram...).

Module này KHÔNG import huggingface_hub, fastapi, fastmcp, hay bất cứ thứ gì
không cần thiết để thao tác trên một thư mục local — để pip install tối
thiểu (chỉ cần Python chuẩn) vẫn dùng được các tool này.

WORKDIR mặc định là thư mục hiện tại (giống Claude Code/Aider) — không còn
khái niệm "Space mục tiêu" phải kéo/đẩy qua mạng nữa. Có thể trỏ tới thư mục
khác bằng biến môi trường AGENT_WORKDIR hoặc gọi set_workdir().
"""

from __future__ import annotations

import ast
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("nao_agent.core")


class PipelineToolError(Exception):
    """Lỗi có chủ ý, hiển thị trực tiếp cho AI/người dùng (không phải bug)."""


# ============================================================
# WORKDIR — thư mục làm việc, mặc định là cwd (local-first)
# ============================================================

def _resolve_workdir() -> Path:
    raw = os.environ.get("AGENT_WORKDIR", "").strip()
    p = Path(raw).expanduser().resolve() if raw else Path.cwd().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


WORKDIR: Path = _resolve_workdir()


def set_workdir(path: str) -> Path:
    """Đổi thư mục làm việc lúc runtime (vd theo cờ --workdir của CLI)."""
    global WORKDIR
    p = Path(path).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    WORKDIR = p
    logger.info("WORKDIR = %s", WORKDIR)
    return WORKDIR


def _safe_path(rel_path: str) -> Path:
    p = (WORKDIR / rel_path).resolve()
    if WORKDIR not in p.parents and p != WORKDIR:
        raise PipelineToolError(f"Path '{rel_path}' nằm ngoài thư mục làm việc, từ chối.")
    return p


# ============================================================
# MINI TERMINAL — phạm vi RỘNG (như 1 người dùng thật): hỗ trợ biến môi
# trường tạm thời/persistent + secret theo tên (xem secrets_manager.py).
# Chỉ còn 1 lớp chặn cho các lệnh HỦY DIỆT không thể hoàn tác ở CẤP HỆ
# THỐNG (không chỉ trong project) — vì lỡ tay ở đây không "Ctrl+Z" lại
# được. Tắt hẳn lớp chặn này bằng AGENT_ALLOW_DESTRUCTIVE=1 nếu bạn chắc
# chắn muốn full quyền, không giới hạn gì (kể cả wipe ổ đĩa).
# ============================================================

_ALLOW_DESTRUCTIVE = os.environ.get("AGENT_ALLOW_DESTRUCTIVE", "").strip() in ("1", "true", "True", "yes")

DESTRUCTIVE_PHRASES = [
    "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf --no-preserve-root",
    ":(){ :|:& };:", "mkfs", "dd if=/dev/zero of=/dev/", "dd if=/dev/random of=/dev/",
    "> /dev/sda", "> /dev/nvme",
]


def _find_destructive_pattern(cmd_clean: str) -> Optional[str]:
    for p in DESTRUCTIVE_PHRASES:
        if p in cmd_clean:
            return p
    return None


# Biến môi trường PERSISTENT (đặt bằng tool_set_env) — áp dụng cho MỌI lần
# exec_terminal tiếp theo, y như `export` trong 1 phiên shell thật. Chỉ
# dùng cho cấu hình KHÔNG nhạy cảm (NODE_ENV, PORT...) — secret thật sự đi
# qua secrets_manager (tham số `secrets` bên dưới) để giá trị không bao
# giờ lộ ra trong hội thoại với AI.
PERSISTENT_ENV: dict = {}


def tool_set_env(key: str, value: str) -> str:
    """Đặt 1 biến môi trường persistent cho các lần exec_terminal sau này
    (giống `export KEY=value`). CHỈ dùng cho cấu hình không nhạy cảm — với
    token/password/API key thật, dùng register_secret() + tham số `secrets`
    của exec_terminal thay vì tool này."""
    if not key or not key.strip():
        raise PipelineToolError("Thiếu 'key'.")
    PERSISTENT_ENV[key.strip()] = "" if value is None else str(value)
    return f"Đã đặt biến môi trường '{key.strip()}' (áp dụng cho các exec_terminal tiếp theo)."


def tool_unset_env(key: str) -> str:
    existed = PERSISTENT_ENV.pop(key.strip(), None) is not None
    return f"Đã bỏ biến môi trường '{key}'." if existed else f"'{key}' chưa từng được đặt."


def tool_list_env() -> str:
    """Liệt kê CÁC BIẾN persistent đã đặt (chỉ tên, không hiện giá trị —
    dù tool_set_env dành cho cấu hình không nhạy cảm, vẫn mặc định che để
    tránh vô tình dán token vào đây thay vì dùng secrets_manager)."""
    if not PERSISTENT_ENV:
        return "(Chưa có biến môi trường persistent nào.)"
    return "\n".join(sorted(PERSISTENT_ENV.keys()))


def exec_terminal(
    command: str,
    timeout: int = 90,
    workdir: Optional[str] = None,
    env: Optional[dict] = None,
    secrets: Optional[list] = None,
) -> str:
    if not command or not command.strip():
        return "(Lệnh rỗng)"
    cmd_clean = command.strip()
    if not _ALLOW_DESTRUCTIVE:
        blocked = _find_destructive_pattern(cmd_clean)
        if blocked:
            return (
                f"LỖI AN TOÀN: Lệnh chứa mẫu HỦY DIỆT không thể hoàn tác ở cấp hệ thống "
                f"('{blocked}') — bị chặn mặc định (không phải chặn theo project, mà chặn "
                f"để tránh phá cả máy). Đặt biến môi trường AGENT_ALLOW_DESTRUCTIVE=1 khi "
                f"khởi động agent nếu bạn chắc chắn muốn bỏ giới hạn này."
            )
    cwd = Path(workdir).resolve() if workdir else WORKDIR

    run_env = os.environ.copy()
    run_env.update(PERSISTENT_ENV)
    if env:
        run_env.update({str(k): "" if v is None else str(v) for k, v in env.items()})

    # Bơm secret theo TÊN thẳng vào env của subprocess con — giá trị thật
    # KHÔNG BAO GIỜ đi qua biến `command`/log, chỉ tồn tại trong tiến trình
    # con. Sau khi chạy xong, mọi occurrence của giá trị thật trong output
    # sẽ bị thay bằng placeholder trước khi trả lại cho AI.
    secret_values: dict = {}
    if secrets:
        from . import secrets_manager

        for name in secrets:
            value = secrets_manager.resolve_secret_value(name)
            run_env[name] = value
            secret_values[name] = value

    try:
        result = subprocess.run(
            cmd_clean, shell=True, cwd=str(cwd), env=run_env,
            capture_output=True, text=True, timeout=timeout,
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        combined = []
        if out:
            combined.append(out)
        if err:
            combined.append(f"[STDERR]\n{err}")
        text = "\n".join(combined)[:4000] if combined else "(Thành công, không có output)"
        for name, value in secret_values.items():
            if value:
                text = text.replace(value, f"***REDACTED:{name}***")
        return text
    except subprocess.TimeoutExpired:
        return f"LỖI TIMEOUT: Tiến trình bị dừng vì chạy quá {timeout}s."
    except PipelineToolError:
        raise
    except Exception as e:
        return f"LỖI HỆ THỐNG: {e}"


# ============================================================
# TOOL IMPLEMENTATIONS
# ============================================================

def tool_list_files(path: str = ".", max_depth: int = 2) -> str:
    root = _safe_path(path)
    lines = []
    base_depth = len(root.parts)
    for p in sorted(root.rglob("*")):
        if any(part.startswith(".") or part in ("node_modules", "__pycache__") for part in p.parts):
            continue
        depth = len(p.parts) - base_depth
        if depth > max_depth:
            continue
        lines.append(f"{'  ' * depth}{'📁' if p.is_dir() else '📄'} {p.name}")
    return "\n".join(lines) or "(rỗng)"


def tool_find_function(path: str, name: str) -> str:
    """Dùng AST tìm CHÍNH XÁC vị trí + nội dung 1 hàm/class/method trong file
    Python — trả về đúng số dòng bắt đầu/kết thúc + SOURCE CODE NGUYÊN VĂN,
    dùng làm `old_str` đảm bảo khớp 100% khi đưa vào edit_file.

    `name` hỗ trợ dạng "function_name" (top-level) hoặc
    "ClassName.method_name" (method trong class)."""
    p = _safe_path(path)
    if not p.exists():
        raise PipelineToolError(f"File '{path}' không tồn tại.")
    source = p.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(p))
    except SyntaxError as e:
        raise PipelineToolError(f"File '{path}' đang lỗi cú pháp, không parse được: {e}")

    target_class = None
    target_name = name
    if "." in name:
        target_class, target_name = name.rsplit(".", 1)

    def _iter_defs(node, class_ctx=None):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                yield child, class_ctx
                if isinstance(child, ast.ClassDef):
                    yield from _iter_defs(child, class_ctx=child.name)
            else:
                yield from _iter_defs(child, class_ctx)

    matches = []
    for node, class_ctx in _iter_defs(tree):
        if node.name != target_name:
            continue
        if target_class is not None and class_ctx != target_class:
            continue
        if target_class is None and class_ctx is not None:
            continue
        matches.append(node)

    if not matches:
        raise PipelineToolError(
            f"Không tìm thấy '{name}' trong '{path}'. Dùng list_files/read_file/"
            f"grep qua exec_terminal để kiểm tra tên chính xác (có phân biệt "
            f"hoa/thường), hoặc nếu là method thì dùng dạng 'ClassName.method_name'."
        )
    if len(matches) > 1:
        lines_found = ", ".join(str(m.lineno) for m in matches)
        raise PipelineToolError(
            f"Tìm thấy {len(matches)} định nghĩa '{name}' trong '{path}' (dòng {lines_found}) "
            f"— tên không rõ ràng. Chỉ rõ hơn (vd 'ClassName.{name}')."
        )

    node = matches[0]
    segment = ast.get_source_segment(source, node)
    if segment is None:
        lines = source.splitlines()
        segment = "\n".join(lines[node.lineno - 1: node.end_lineno])
    end_line = getattr(node, "end_lineno", node.lineno)
    return (
        f"Tìm thấy '{name}' trong '{path}', dòng {node.lineno}-{end_line}.\n"
        f"SOURCE NGUYÊN VĂN (dùng đúng đoạn này làm old_str cho edit_file):\n"
        f"{segment}"
    )


def tool_read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    p = _safe_path(path)
    if not p.exists():
        raise PipelineToolError(f"File '{path}' không tồn tại.")
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    s = (start_line or 1) - 1
    e = end_line or len(lines)
    return "\n".join(lines[s:e])


def _py_compile_check(p: Path) -> Optional[str]:
    if p.suffix != ".py":
        return None
    res = subprocess.run([sys.executable, "-m", "py_compile", str(p)], capture_output=True, text=True)
    return res.stderr.strip() if res.returncode != 0 else None


def tool_write_file(path: str, content: str) -> str:
    """Chỉ dùng để TẠO FILE MỚI (path chưa tồn tại). KHÔNG có lối tắt ghi
    đè: nếu file đã tồn tại, tool này LUÔN từ chối, không có tham số nào
    bật lại việc ghi đè cả file. Muốn thay đổi nội dung file đã có -> dùng
    edit_file (patch old_str/new_str). Muốn viết lại toàn bộ 1 file đã có
    -> delete_file(path) rồi write_file(path, ...) lại, đây là 2 bước tách
    biệt có chủ ý để không bao giờ vô tình xóa mất code khi patch nhầm."""
    p = _safe_path(path)
    if p.exists():
        old_size = p.stat().st_size
        return (
            f"LỖI: '{path}' đã tồn tại ({old_size} byte). write_file KHÔNG được phép ghi đè "
            f"file đã có (không có tham số overwrite/confirmed nào cả) — dùng edit_file "
            f"(old_str/new_str) để patch đúng phần cần sửa, đọc kỹ file bằng read_file trước "
            f"nếu chưa chắc nội dung hiện tại. Nếu THỰC SỰ cần viết lại toàn bộ file, gọi "
            f"delete_file('{path}') trước rồi mới write_file lại."
        )
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    err = _py_compile_check(p)
    if err:
        return f"Đã ghi '{path}' NHƯNG lỗi cú pháp:\n{err}\nSửa lại trước khi commit."
    return f"Đã ghi '{path}' ({len(content)} ký tự). Compile OK." if p.suffix == ".py" else f"Đã ghi '{path}'."


def tool_edit_file(path: str, old_str: str = None, new_str: str = None, **kwargs) -> str:
    p = _safe_path(path)
    if not p.exists():
        raise PipelineToolError(f"File '{path}' không tồn tại.")

    # Bao dung tham số — AI hay gọi edit_file nhưng truyền content/code.
    full_content = (
        kwargs.get("content") or kwargs.get("new_content")
        or kwargs.get("code") or kwargs.get("file_content")
    )
    if full_content and not old_str:
        logger.info("AI gọi edit_file nhưng truyền content -> tự chuyển sang write_file.")
        return tool_write_file(path, full_content)

    if not old_str or not new_str:
        raise PipelineToolError(
            "LỖI THAM SỐ: edit_file yêu cầu 'old_str' và 'new_str'. "
            "Nếu muốn GHI ĐÈ toàn bộ file, hãy dùng tool `write_file` với tham số `content`."
        )

    text = p.read_text(encoding="utf-8")
    if old_str not in text:
        raise PipelineToolError(f"Không tìm thấy chuỗi cần thay trong '{path}'. Hãy dùng read_file kiểm tra lại.")
    if text.count(old_str) > 1:
        raise PipelineToolError(f"Chuỗi xuất hiện {text.count(old_str)} lần, cần unique hơn.")

    p.write_text(text.replace(old_str, new_str), encoding="utf-8")
    err = _py_compile_check(p)
    if err:
        return f"Đã sửa '{path}' NHƯNG lỗi cú pháp:\n{err}\nSửa lại trước khi commit."
    return f"Đã sửa '{path}'. Compile OK." if p.suffix == ".py" else f"Đã sửa '{path}'."


def tool_delete_file(path: str) -> str:
    p = _safe_path(path)
    if not p.exists():
        raise PipelineToolError(f"File '{path}' không tồn tại.")
    p.unlink()
    return f"Đã xoá '{path}'."


def tool_exec_terminal(
    command: str,
    timeout: int = 90,
    env: Optional[dict] = None,
    secrets: Optional[list] = None,
) -> str:
    """Chạy 1 lệnh shell trong WORKDIR, như 1 người dùng thật:
    - `env`: dict biến môi trường CHỈ áp dụng cho lần gọi này (vd
      {"NODE_ENV": "production"}).
    - `secrets`: danh sách TÊN secret đã đăng ký qua register_secret() —
      giá trị thật được bơm vào env của lệnh này rồi tự bị che trong output
      trả về, AI không bao giờ nhìn thấy giá trị thật.
    Biến persistent đặt bằng set_env() luôn được áp dụng thêm vào."""
    return exec_terminal(command=command, timeout=timeout, workdir=str(WORKDIR), env=env, secrets=secrets)


def tool_complete_task(summary: str = "Đã hoàn thành nhiệm vụ.", notes: str = "") -> str:
    return f"ĐÃ YÊU CẦU HOÀN THÀNH: {summary}" + (f"\n{notes}" if notes else "")


# Bảng tool cốt lõi — dùng chung cho MCP server, REST API (legacy) và CLI agent.
# Lưu ý: write_file KHÔNG có bản "confirmed/overwrite" — chỉ tạo/sửa/xóa,
# không bao giờ ghi đè cả file (xem tool_write_file). Tool secret
# (register_secret/list_secrets/forget_secret) nằm ở secrets_manager.SECRET_TOOLS,
# được gộp thêm ở mcp_server.py/cli_agent.py để tránh import vòng.
CORE_TOOLS = {
    "list_files": tool_list_files,
    "read_file": tool_read_file,
    "find_function": tool_find_function,
    "write_file": tool_write_file,
    "edit_file": tool_edit_file,
    "delete_file": tool_delete_file,
    "exec_terminal": tool_exec_terminal,
    "set_env": tool_set_env,
    "unset_env": tool_unset_env,
    "list_env": tool_list_env,
    "complete_task": tool_complete_task,
}

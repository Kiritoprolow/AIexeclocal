"""
nao_agent.secrets_manager
==========================
Cơ chế "secret theo TÊN" — bạn lưu secret thật (token, API key, password...)
trong 1 FILE bất kỳ, ở BẤT KỲ ĐÂU trên máy (vd `~/.secrets/github_token`,
`/etc/myapp/db_password.txt`...), rồi chỉ cần đăng ký MỘT LẦN bằng:

    register_secret(name="GITHUB_TOKEN", path="~/.secrets/github_token")

Từ đó AI chỉ thao tác qua NAME ("GITHUB_TOKEN") — không bao giờ tool nào
đọc/in giá trị thật ra hội thoại:

- File cấu hình (mặc định `~/.nao_agent/secrets.json`, đổi bằng biến môi
  trường `AGENT_SECRETS_FILE`) CHỈ lưu mapping name -> path, KHÔNG BAO GIỜ
  lưu giá trị thật.
- Giá trị thật chỉ được đọc từ đĩa lúc `exec_terminal(..., secrets=[...])`
  chạy, bơm THẲNG vào biến môi trường của tiến trình con — không đi qua
  bất kỳ log/tin nhắn nào.
- Sau khi lệnh chạy xong, output (stdout/stderr) được quét lại: nếu giá
  trị thật xuất hiện nguyên văn, bị thay bằng "***REDACTED:<name>***"
  trước khi trả về cho AI (xem core.exec_terminal).
- `list_secrets()` chỉ trả về TÊN + đường dẫn đã đăng ký, không bao giờ
  trả về nội dung file.

Nhờ vậy bạn có thể để AI dùng token GitHub, API key, mật khẩu DB... trong
các lệnh terminal (git, curl, psql...) mà giá trị thật KHÔNG BAO GIỜ xuất
hiện trong lịch sử chat/log của client MCP.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

from . import core

_DEFAULT_CONFIG = Path.home() / ".nao_agent" / "secrets.json"


def _config_path() -> Path:
    raw = os.environ.get("AGENT_SECRETS_FILE", "").strip()
    return Path(raw).expanduser().resolve() if raw else _DEFAULT_CONFIG


def _load_map() -> Dict[str, str]:
    p = _config_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_map(mapping: Dict[str, str]) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(p, 0o600)  # chỉ owner đọc/ghi được file mapping này
    except Exception:
        pass


def tool_register_secret(name: str, path: str) -> str:
    """Đăng ký 1 secret theo TÊN, trỏ tới file chứa giá trị thật — path có
    thể ở BẤT KỲ thư mục nào trên máy bạn (không cần copy vào project).
    Tool này CHỈ lưu lại đường dẫn, KHÔNG đọc/không in giá trị bên trong
    file ra kết quả trả về. Từ sau khi đăng ký, chỉ cần nhắc tên (vd
    "dùng secret GITHUB_TOKEN") thay vì dán giá trị thật vào chat."""
    if not name or not name.strip():
        raise core.PipelineToolError("Thiếu 'name' cho secret.")
    name = name.strip()
    if not path or not path.strip():
        raise core.PipelineToolError("Thiếu 'path' tới file chứa giá trị secret.")
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise core.PipelineToolError(
            f"Không tìm thấy file tại '{resolved}'. Tạo file này (chỉ chứa giá trị secret, "
            f"không thêm dấu ngoặc/biến môi trường) rồi đăng ký lại."
        )
    mapping = _load_map()
    mapping[name] = str(resolved)
    _save_map(mapping)
    return (
        f"Đã đăng ký secret '{name}' (trỏ tới 1 file trên máy bạn). "
        f"Từ giờ dùng exec_terminal(..., secrets=[\"{name}\"]) để lệnh có quyền truy cập "
        f"giá trị này qua biến môi trường '{name}' — KHÔNG lưu, KHÔNG hiện giá trị ở đây."
    )


def tool_list_secrets() -> str:
    """Liệt kê TÊN + đường dẫn các secret đã đăng ký. KHÔNG BAO GIỜ trả về
    nội dung/giá trị thật của secret."""
    mapping = _load_map()
    if not mapping:
        return "(Chưa có secret nào được đăng ký. Dùng register_secret(name, path).)"
    return "\n".join(f"- {name}  ->  {path}" for name, path in sorted(mapping.items()))


def tool_forget_secret(name: str) -> str:
    """Gỡ đăng ký 1 secret theo tên — chỉ xóa mapping, KHÔNG đụng tới file
    thật trên đĩa."""
    name = (name or "").strip()
    mapping = _load_map()
    if name not in mapping:
        raise core.PipelineToolError(f"Không có secret '{name}' đã đăng ký.")
    del mapping[name]
    _save_map(mapping)
    return f"Đã gỡ đăng ký secret '{name}' (file gốc trên đĩa vẫn còn nguyên)."


def resolve_secret_value(name: str) -> str:
    """CHỈ dùng NỘI BỘ (core.exec_terminal gọi để bơm vào env subprocess).
    KHÔNG BAO GIỜ gọi hàm này rồi trả kết quả thẳng ra cho AI/người dùng —
    mọi tool công khai (list_secrets...) không bao giờ dùng hàm này để in
    giá trị ra."""
    mapping = _load_map()
    path = mapping.get(name)
    if not path:
        raise core.PipelineToolError(
            f"Secret '{name}' chưa được đăng ký — dùng register_secret(name, path) trước."
        )
    p = Path(path)
    if not p.exists():
        raise core.PipelineToolError(
            f"File secret cho '{name}' không còn tồn tại tại '{path}' (đã bị xóa/di chuyển?)."
        )
    return p.read_text(encoding="utf-8").strip()


def known_names() -> List[str]:
    return list(_load_map().keys())


# Bảng tool secret — gộp thêm vào mcp_server.py/cli_agent.py bên cạnh
# core.CORE_TOOLS (tách riêng module để tránh import vòng: core.exec_terminal
# chỉ import module này lười biếng lúc thực sự cần resolve_secret_value).
SECRET_TOOLS = {
    "register_secret": tool_register_secret,
    "list_secrets": tool_list_secrets,
    "forget_secret": tool_forget_secret,
}

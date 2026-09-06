"""
nao_agent.cli_agent
====================
Chế độ CLI độc lập: `nao-agent task "mô tả việc cần làm"` — tự gọi thẳng
OpenAI API (function/tool calling) để hoàn thành nhiệm vụ trên WORKDIR,
KHÔNG cần bất kỳ client MCP nào (Claude Desktop, Cursor...) — chỉ cần
OPENAI_API_KEY. Dùng cho ai muốn 1 lệnh chạy 1 phát, kiểu Aider/Codex CLI.

Vòng lặp: gửi task -> model chọn gọi tool -> agent thực thi tool cục bộ ->
trả kết quả lại cho model -> lặp tới khi model gọi complete_task hoặc hết
số lượt tối đa (an toàn, tránh vòng lặp vô hạn tốn tiền API).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from . import core
from . import secrets_manager

logger = logging.getLogger("nao_agent.cli_agent")

DEFAULT_MODEL = "gpt-5.1"  # đổi bằng biến môi trường OPENAI_MODEL nếu cần
MAX_TURNS = 40

SYSTEM_PROMPT = (
    "Bạn là 1 coding agent chạy LOCAL trên máy người dùng, có toàn quyền "
    "đọc/sửa/xóa file, tạo file mới, và chạy lệnh shell (kể cả đặt biến "
    "môi trường) trong thư mục làm việc hiện tại thông qua các tool được "
    "cung cấp. write_file CHỈ tạo file MỚI, KHÔNG BAO GIỜ ghi đè file đã "
    "tồn tại — luôn dùng edit_file (patch old_str/new_str) để sửa file đã "
    "có; nếu thực sự cần viết lại toàn bộ 1 file, gọi delete_file rồi mới "
    "write_file lại. Luôn đọc file bằng read_file trước khi sửa. Với "
    "token/API key/password thật, KHÔNG BAO GIỜ yêu cầu người dùng dán "
    "giá trị vào chat — hướng dẫn họ dùng register_secret(name, path) trỏ "
    "tới 1 file trên máy họ, rồi dùng tên đó qua tham số `secrets` của "
    "exec_terminal. Khi xong việc, PHẢI gọi tool complete_task với tóm "
    "tắt những gì đã làm."
)

_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Liệt kê cây thư mục của project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "max_depth": {"type": "integer", "default": 2},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Đọc nội dung 1 file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_function",
            "description": "Tìm chính xác source code 1 hàm/class/method Python bằng AST.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "name": {"type": "string"},
                },
                "required": ["path", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Tạo file MỚI. Nếu file đã tồn tại sẽ LUÔN bị từ chối — không có "
                            "tham số nào bật ghi đè; dùng edit_file để patch file đã có.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Thay old_str bằng new_str trong 1 file đã có (old_str phải khớp chính xác, duy nhất).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_str": {"type": "string"},
                    "new_str": {"type": "string"},
                },
                "required": ["path", "old_str", "new_str"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Xóa 1 file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "exec_terminal",
            "description": "Chạy 1 lệnh shell trong thư mục làm việc, như 1 người dùng thật "
                            "(đặt biến môi trường, git, ssh, curl, cài package...).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "default": 90},
                    "env": {
                        "type": "object",
                        "description": "Biến môi trường chỉ áp dụng cho lệnh này.",
                    },
                    "secrets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tên các secret đã đăng ký qua register_secret() cần "
                                        "bơm vào env của lệnh này (giá trị thật không lộ ra).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_env",
            "description": "Đặt 1 biến môi trường persistent cho các exec_terminal sau này "
                            "(không dùng cho secret thật — dùng register_secret cho việc đó).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unset_env",
            "description": "Bỏ 1 biến môi trường persistent đã đặt bằng set_env.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_env",
            "description": "Liệt kê tên các biến môi trường persistent đang được đặt.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "register_secret",
            "description": "Đăng ký 1 secret theo tên, trỏ tới file chứa giá trị thật ở bất "
                            "kỳ đâu trên máy người dùng. Không đọc/in giá trị ra.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["name", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_secrets",
            "description": "Liệt kê tên + đường dẫn các secret đã đăng ký (không hiện giá trị).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_secret",
            "description": "Gỡ đăng ký 1 secret theo tên (không xóa file thật trên đĩa).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Gọi khi đã hoàn thành nhiệm vụ, kèm tóm tắt những gì đã làm.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["summary"],
            },
        },
    },
]

_TOOL_IMPLS = {
    "list_files": core.tool_list_files,
    "read_file": core.tool_read_file,
    "find_function": core.tool_find_function,
    "write_file": core.tool_write_file,
    "edit_file": core.tool_edit_file,
    "delete_file": core.tool_delete_file,
    "exec_terminal": core.tool_exec_terminal,
    "set_env": core.tool_set_env,
    "unset_env": core.tool_unset_env,
    "list_env": core.tool_list_env,
    "register_secret": secrets_manager.tool_register_secret,
    "list_secrets": secrets_manager.tool_list_secrets,
    "forget_secret": secrets_manager.tool_forget_secret,
    "complete_task": core.tool_complete_task,
}


def _run_tool(name: str, args: Dict[str, Any]) -> str:
    impl = _TOOL_IMPLS.get(name)
    if not impl:
        return f"LỖI: không có tool '{name}'."
    try:
        return str(impl(**args))
    except core.PipelineToolError as e:
        return f"LỖI: {e}"
    except TypeError as e:
        return f"LỖI THAM SỐ cho '{name}': {e}"
    except Exception as e:
        return f"LỖI HỆ THỐNG: {e}"


def run_task(task: str, model: str = DEFAULT_MODEL, max_turns: int = MAX_TURNS, verbose: bool = True) -> str:
    """Chạy 1 vòng lặp agent gọi thẳng OpenAI Chat Completions API (tool
    calling) để hoàn thành `task` trên core.WORKDIR. Trả về summary cuối."""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "Cần cài package 'openai' để dùng chế độ CLI (`pip install openai`)."
        ) from e

    client = OpenAI()  # đọc OPENAI_API_KEY từ biến môi trường

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Thư mục làm việc: {core.WORKDIR}\n\nNhiệm vụ: {task}"},
    ]

    for turn in range(1, max_turns + 1):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=_TOOL_SCHEMAS,
        )
        choice = response.choices[0]
        msg = choice.message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            # Model trả lời bằng text thường, không gọi tool -> coi như xong.
            return msg.content or "(Model không trả về nội dung.)"

        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if verbose:
                logger.info("[turn %d] gọi tool %s(%s)", turn, name, args)

            result = _run_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result[:8000],
            })

            if name == "complete_task":
                return result

    return f"Dừng lại sau {max_turns} lượt mà chưa gọi complete_task — nhiệm vụ có thể chưa xong hẳn."

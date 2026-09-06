"""
nao_agent.__main__
====================
Entry point CLI:

    nao-agent                          # MẶC ĐỊNH: MCP server qua stdio (local)
    nao-agent serve --http             # legacy: MCP-over-HTTP + REST /api/*
    nao-agent serve --http --host 0.0.0.0 --port 7860   # host remote (vd HF Space)
    nao-agent task "sửa lỗi ở hàm foo trong app.py"      # CLI 1 phát, gọi OpenAI trực tiếp
    nao-agent --workdir /path/to/project serve           # trỏ tới thư mục khác

Không truyền gì cả tương đương `nao-agent serve` (stdio) — vừa cài xong là
add được thẳng vào Claude Desktop / Cursor / VS Code mà không cần cấu hình
gì thêm ngoài đường dẫn tới lệnh này.
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import core

logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("nao_agent")


def _maybe_pull_space():
    from . import space_ops
    if space_ops.enabled():
        space_ops.pull_target_space()
        space_ops.start_health_poll_loop()
        space_ops.start_telegram_poll_loop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nao-agent", description="Coding agent chạy local qua MCP.")
    parser.add_argument("--workdir", help="Thư mục làm việc (mặc định: thư mục hiện tại, hoặc $AGENT_WORKDIR).")

    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="Chạy agent như 1 MCP server (mặc định: stdio).")
    p_serve.add_argument("--http", action="store_true", help="Dùng transport HTTP thay vì stdio (chế độ legacy/remote).")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host khi dùng --http (mặc định 127.0.0.1, chỉ máy này gọi được).")
    p_serve.add_argument("--port", type=int, default=8765, help="Port khi dùng --http.")
    p_serve.add_argument("--no-rest-api", action="store_true", help="Tắt REST '/api/*' khi dùng --http (chỉ giữ MCP-over-HTTP).")

    p_task = sub.add_parser("task", help="Chạy 1 nhiệm vụ 1 lần qua OpenAI API trực tiếp (không cần client MCP).")
    p_task.add_argument("description", help="Mô tả nhiệm vụ cần agent thực hiện.")
    p_task.add_argument("--model", default=None, help="Model OpenAI (mặc định: $OPENAI_MODEL hoặc gpt-5.1).")
    p_task.add_argument("--max-turns", type=int, default=None)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.workdir:
        core.set_workdir(args.workdir)

    if args.command in (None, "serve"):
        _maybe_pull_space()
        from . import mcp_server

        use_http = getattr(args, "http", False)
        if use_http:
            mcp_server.run_http(
                host=args.host, port=args.port,
                mount_rest_api=not getattr(args, "no_rest_api", False),
            )
        else:
            mcp_server.run_stdio()
        return 0

    if args.command == "task":
        from . import cli_agent
        import os

        model = args.model or os.environ.get("OPENAI_MODEL") or cli_agent.DEFAULT_MODEL
        max_turns = args.max_turns or cli_agent.MAX_TURNS
        result = cli_agent.run_task(args.description, model=model, max_turns=max_turns)
        print(result)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

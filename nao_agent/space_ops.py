"""
nao_agent.space_ops
====================
Toàn bộ tính năng ĐẶC THÙ cho việc host trên/điều khiển 1 Hugging Face Space
từ xa: kéo code Space mục tiêu về, đẩy code lên, restart, giám sát sức khỏe
qua Telegram. Đây KHÔNG phải core của agent local — module này CHỈ được
import khi người dùng bật HF_SPACE_MODE=1 (biến môi trường), để:

- Ai chỉ cần agent local thuần (đa số người dùng open-source) không bắt buộc
  phải cài `huggingface_hub` hay quan tâm khái niệm "Space mục tiêu".
- Người vẫn muốn dùng lại kiểu cũ (điều khiển 1 HF Space từ xa qua GPT/MCP)
  vẫn dùng được y nguyên, chỉ cần bật cờ.

Kích hoạt bằng:
    HF_SPACE_MODE=1
    TARGET_SPACE_ID=<user>/<space>
    HF_TOKEN=hf_xxx
    (tuỳ chọn) TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import json
import logging
import os
import sys
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from . import core

logger = logging.getLogger("nao_agent.space_ops")

HF_SPACE_MODE = os.environ.get("HF_SPACE_MODE", "").strip() in ("1", "true", "True", "yes")

HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()
TARGET_SPACE_ID = (
    os.environ.get("TARGET_SPACE_ID", "").strip()
    or os.environ.get("SPACE_ID", "").strip()
)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

_ERROR_STAGES = {
    "RUNTIME_ERROR", "BUILD_ERROR", "APP_STARTING_ERROR",
    "CONFIG_ERROR", "NO_APP_FILE",
}
_health_state = {"last_autofix_ts": 0.0}
_AUTOFIX_COOLDOWN_SEC = 600

_hf_api = None


def enabled() -> bool:
    return HF_SPACE_MODE


def _get_hf_api():
    global _hf_api
    if _hf_api is None:
        from huggingface_hub import HfApi
        _hf_api = HfApi(token=HF_TOKEN)
    return _hf_api


def pull_target_space() -> None:
    """Kéo code Space mục tiêu về WORKDIR, rồi best-effort cài
    requirements.txt của Space đó (để exec_terminal chạy/import được code
    thật, không chỉ py_compile)."""
    if not (TARGET_SPACE_ID and HF_TOKEN):
        logger.info("HF_SPACE_MODE bật nhưng thiếu TARGET_SPACE_ID/HF_TOKEN — bỏ qua pull.")
        return
    from huggingface_hub import snapshot_download

    try:
        snapshot_download(
            repo_id=TARGET_SPACE_ID,
            repo_type="space",
            local_dir=str(core.WORKDIR),
            token=HF_TOKEN,
        )
        logger.info("Đã kéo code Space mục tiêu '%s' về %s", TARGET_SPACE_ID, core.WORKDIR)
    except Exception as e:
        logger.error("Không kéo được code Space mục tiêu '%s': %s", TARGET_SPACE_ID, e)
        return

    req_file = core.WORKDIR / "requirements.txt"
    if req_file.exists():
        try:
            logger.info("⏳ Đang cài dependency của Space mục tiêu (requirements.txt)...")
            res = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file), "--quiet"],
                capture_output=True, text=True, timeout=600,
            )
            if res.returncode == 0:
                logger.info("✅ Đã cài xong dependency của Space mục tiêu.")
            else:
                logger.warning(
                    "⚠️ Cài dependency Space mục tiêu lỗi (không chặn khởi động): %s",
                    res.stderr[-2000:],
                )
        except Exception as e:
            logger.warning("⚠️ Không cài được requirements.txt của Space mục tiêu: %s", e)


def tool_push_to_space(paths: list) -> str:
    if not TARGET_SPACE_ID:
        raise core.PipelineToolError("Không tìm thấy TARGET_SPACE_ID.")
    if not HF_TOKEN:
        raise core.PipelineToolError("Thiếu HF_TOKEN.")
    hf_api = _get_hf_api()

    to_upload = []
    to_delete = []
    for rel in paths:
        p = core._safe_path(rel)
        norm_path = str(p.relative_to(core.WORKDIR)).replace(os.sep, "/")
        if p.exists():
            err = core._py_compile_check(p)
            if err:
                return f"Dừng lại: '{rel}' còn lỗi cú pháp:\n{err}"
            to_upload.append((p, norm_path))
        else:
            to_delete.append(norm_path)

    for p, norm_path in to_upload:
        hf_api.upload_file(
            path_or_fileobj=str(p), path_in_repo=norm_path,
            repo_id=TARGET_SPACE_ID, repo_type="space",
            commit_message=f"agent: cập nhật {norm_path}",
        )
    for norm_path in to_delete:
        try:
            hf_api.delete_file(
                path_in_repo=norm_path, repo_id=TARGET_SPACE_ID, repo_type="space",
                commit_message=f"agent: xóa {norm_path}",
            )
        except Exception as e:
            return f"Đã push {len(to_upload)} file, nhưng xóa '{norm_path}' trên Space thất bại: {e}"

    parts = []
    if to_upload:
        parts.append(f"cập nhật {len(to_upload)} file ({', '.join(n for _, n in to_upload)})")
    if to_delete:
        parts.append(f"xóa {len(to_delete)} file ({', '.join(to_delete)})")
    return f"Đã push lên Space mục tiêu '{TARGET_SPACE_ID}': " + "; ".join(parts) + "."


def tool_restart_space() -> str:
    if not TARGET_SPACE_ID or not HF_TOKEN:
        raise core.PipelineToolError("Thiếu TARGET_SPACE_ID hoặc HF_TOKEN.")
    _get_hf_api().restart_space(repo_id=TARGET_SPACE_ID)
    return f"Đã gửi lệnh restart cho Space mục tiêu '{TARGET_SPACE_ID}'."


def tool_refresh_context(max_depth: int = 3) -> str:
    tree = core.tool_list_files(".", max_depth=max_depth)
    return f"[Bản chụp cây thư mục Space Mục Tiêu '{TARGET_SPACE_ID}']\n{tree}"


SPACE_TOOLS = {
    "push_to_space": tool_push_to_space,
    "restart_space": tool_restart_space,
    "refresh_context": tool_refresh_context,
}


# ============================================================
# TELEGRAM + GIÁM SÁT SỨC KHỎE (tuỳ chọn, chỉ chạy khi có token)
# ============================================================

def _telegram_send(text: str) -> None:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    import requests

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for i in range(0, len(text), 4000):
        try:
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text[i:i + 4000]}, timeout=15)
        except Exception:
            pass


def _fetch_space_run_logs(repo_id: str, max_chars: int = 60_000, read_timeout_sec: int = 8) -> str:
    if not HF_TOKEN:
        return "(Không có HF_TOKEN nên không cào được log.)"
    import requests

    url = f"https://huggingface.co/api/spaces/{repo_id}/logs/run"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    lines = []
    total_len = 0
    try:
        with requests.get(url, headers=headers, stream=True, timeout=read_timeout_sec) as resp:
            resp.raise_for_status()
            start = time.time()
            for raw_line in resp.iter_lines(decode_unicode=True):
                if time.time() - start > read_timeout_sec:
                    break
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                payload = raw_line[len("data:"):].strip()
                if not payload:
                    continue
                try:
                    obj = json.loads(payload)
                    text = obj.get("data") or obj.get("text") or str(obj)
                except Exception:
                    text = payload
                lines.append(text)
                total_len += len(text)
                if total_len >= max_chars:
                    break
    except Exception as e:
        return f"(Lỗi khi cào log: {e})"
    if not lines:
        return "(Không lấy được dòng log nào — Space có thể chưa từng chạy, hoặc endpoint log đã đổi.)"
    return "\n".join(lines)[-max_chars:]


def check_space_health(repo_id: Optional[str] = None) -> dict:
    target = repo_id or TARGET_SPACE_ID
    if not target:
        return {"stage": None, "ok": True, "message": "Chưa cấu hình TARGET_SPACE_ID."}
    try:
        runtime = _get_hf_api().get_space_runtime(repo_id=target)
        stage = getattr(runtime, "stage", None) or "UNKNOWN"
    except Exception as e:
        return {"stage": None, "ok": True, "message": f"Không kiểm tra được trạng thái: {e}"}
    ok = stage not in _ERROR_STAGES
    return {"stage": stage, "ok": ok, "message": f"Trạng thái Space: {stage}"}


def trigger_space_autofix(force: bool = False) -> str:
    health = check_space_health()
    stage = health["stage"]
    if health["ok"]:
        return f"✅ Space OK ({stage or 'không rõ'})."

    now = time.time()
    if not force and (now - _health_state["last_autofix_ts"] < _AUTOFIX_COOLDOWN_SEC):
        remain = int(_AUTOFIX_COOLDOWN_SEC - (now - _health_state["last_autofix_ts"]))
        return f"⚠️ Space đang lỗi ({stage}) nhưng vừa báo gần đây, đợi thêm {remain}s để tránh spam."

    logs = _fetch_space_run_logs(TARGET_SPACE_ID)
    _health_state["last_autofix_ts"] = now
    _telegram_send(
        f"🚨 **Space '{TARGET_SPACE_ID}' đang lỗi ({stage})!**\n\n"
        f"Log gần nhất:\n```\n{logs[-3500:]}\n```\n\n"
        "👉 Mở client MCP đã gắn tới agent này và nhờ AI đọc log, sửa lỗi rồi push_to_space."
    )
    return f"🚨 Space đang lỗi ({stage}) — đã báo qua Telegram kèm log."


def start_health_poll_loop(interval_sec: int = 90) -> Optional[threading.Thread]:
    if not TARGET_SPACE_ID:
        return None

    def _loop():
        while True:
            try:
                trigger_space_autofix(force=False)
            except Exception as e:
                logger.error("Lỗi health poll: %s", e)
            time.sleep(interval_sec)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t


def start_telegram_poll_loop() -> Optional[threading.Thread]:
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return None
    import requests

    def _loop():
        offset = 0
        base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        while True:
            try:
                resp = requests.get(f"{base}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=40)
                data = resp.json()
            except Exception:
                time.sleep(5)
                continue
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or {}
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = (msg.get("text") or "").strip()
                if not text or chat_id != str(TELEGRAM_CHAT_ID):
                    continue
                if text == "/status":
                    h = check_space_health()
                    _telegram_send(f"⚙️ **Trạng thái Space:** {h['message']}")
                elif text.startswith("/checkspace"):
                    force = "force" in text
                    _telegram_send(trigger_space_autofix(force=force))
                else:
                    _telegram_send(
                        "ℹ️ Bot này chỉ giám sát Space (/status, /checkspace [force])."
                    )

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t

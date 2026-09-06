# 🐧 nao-coding-agent

**Biến bất kỳ AI nào (Claude, Cursor, Copilot, Codex CLI...) thành 1 coding
agent chạy 100% LOCAL trên máy bạn** — đọc file, sửa code, xóa file, chạy
terminal như 1 lập trình viên thật, không cần server từ xa, không cần
`curl`, không cần token, không gửi 1 dòng code nào của bạn đi đâu cả ngoài
đúng client AI bạn đang dùng.

> Chạy qua giao thức **MCP** (Model Context Protocol), transport `stdio`:
> client AI tự khởi động `nao-agent` làm subprocess và nói chuyện qua
> stdin/stdout. Cắm dây một lần, dùng mãi mãi.

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/protocol-MCP-purple.svg)](https://modelcontextprotocol.io)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#-đóng-góp)

---

## Mục lục

- [Vì sao có project này](#vì-sao-có-project-này)
- [Tính năng nổi bật](#tính-năng-nổi-bật)
- [Cài đặt](#cài-đặt)
- [Bắt đầu trong 60 giây](#bắt-đầu-trong-60-giây)
  - [Claude Desktop](#claude-desktop)
  - [Cursor](#cursor)
  - [VS Code (Copilot Chat / MCP)](#vs-code-copilot-chat--mcp)
  - [Codex CLI / client MCP khác](#codex-cli--client-mcp-khác)
- [Cách dùng hằng ngày](#cách-dùng-hằng-ngày)
- [Danh sách tool đầy đủ](#danh-sách-tool-đầy-đủ)
- [Ghi file: chỉ tạo mới / sửa / xóa — không có đường ghi đè](#ghi-file-chỉ-tạo-mới--sửa--xóa--không-có-đường-ghi-đè)
- [Secret theo tên — dùng token/API key mà AI không bao giờ thấy giá trị thật](#secret-theo-tên--dùng-tokenapi-key-mà-ai-không-bao-giờ-thấy-giá-trị-thật)
- [Terminal: mạnh như 1 người dùng thật](#terminal-mạnh-như-1-người-dùng-thật)
- [Chế độ nâng cao](#chế-độ-nâng-cao)
  - [1. CLI 1 phát (không cần client MCP)](#1-cli-1-phát-không-cần-client-mcp)
  - [2. HTTP / legacy (deploy remote)](#2-http--legacy-deploy-remote)
  - [3. Hugging Face Space mode](#3-hugging-face-space-mode)
- [Biến môi trường — tra cứu nhanh](#biến-môi-trường--tra-cứu-nhanh)
- [Kiến trúc](#kiến-trúc)
- [An toàn & mô hình tin cậy](#an-toàn--mô-hình-tin-cậy)
- [Câu hỏi thường gặp](#câu-hỏi-thường-gặp)
- [Đóng góp](#đóng-góp)
- [Giấy phép](#giấy-phép)

---

## Vì sao có project này

Hầu hết "AI coding agent" hiện nay đều bắt bạn chọn 1 trong 2 điều bạn
không muốn đánh đổi:

1. **Dán code lên 1 dashboard/SaaS** để AI đọc được thư mục của bạn, hoặc
2. Tự dựng server, cấu hình token, deploy đâu đó chỉ để AI local của bạn
   gọi được vào máy chính bạn.

**nao-coding-agent bỏ qua cả 2.** Nó là 1 tiến trình MCP nhỏ, gọn, chạy
ngay trên máy bạn, được chính client AI của bạn (Claude Desktop, Cursor,
VS Code, Codex CLI...) khởi động như 1 subprocess con. Không mạng, không
cloud, không bên thứ 3 nào chen giữa bạn và AI của bạn — cài xong là dùng,
giống hệt cách `git`, `npm` hay bất kỳ CLI tool nào bạn đã quen thuộc.

Triết lý thiết kế xuyên suốt: **cho AI đủ quyền để làm việc thật sự hữu
ích (đọc/sửa/xóa file, chạy terminal như người dùng thật), nhưng vẫn có
những rào chắn tối thiểu, rõ ràng, không thể lách qua đường tắt** ở đúng
những chỗ một sai sót của AI là không thể hoàn tác (ghi đè mất code, phá
cả hệ thống, làm lộ secret).

## Tính năng nổi bật

| | |
|---|---|
| 🔌 **Zero-config, zero-server** | Không HTTP, không token, không deploy — chỉ 1 dòng lệnh trong config của client MCP bạn đã có sẵn. |
| 🧠 **Tương thích mọi client MCP** | Claude Desktop, Cursor, VS Code Copilot Chat, Codex CLI, hoặc bất kỳ ai nói được `stdio`. |
| 📝 **Sửa file an toàn** | `write_file` chỉ tạo file mới — **không có cách nào ghi đè 1 file đã tồn tại**. Sửa code luôn đi qua `edit_file` (patch có mục tiêu) hoặc `find_function` (định vị chính xác bằng AST). |
| 🔐 **Secret theo tên, không lộ giá trị** | Lưu token/API key/password ở bất kỳ file nào trên máy bạn, đăng ký 1 lần bằng tên — AI dùng được trong lệnh terminal mà **không bao giờ nhìn thấy giá trị thật**, kể cả trong log. |
| 🖥️ **Terminal như người dùng thật** | Đặt biến môi trường (tạm thời hoặc persistent), chạy `git`, `ssh`, `curl`, cài package... — chỉ chặn duy nhất nhóm lệnh phá hủy không thể hoàn tác ở cấp cả máy. |
| 🌲 **Định vị code chính xác bằng AST** | `find_function` tìm đúng hàm/class/method trong file Python, trả về source nguyên văn để dùng ngay làm `old_str` cho `edit_file` — không còn kiểu "AI đoán mò dòng". |
| 🧩 **Mở rộng được** | Chế độ CLI gọi thẳng OpenAI, HTTP/REST legacy để deploy remote, và chế độ điều khiển 1 Hugging Face Space từ xa (kèm giám sát qua Telegram) — tất cả đều tùy chọn, tắt mặc định. |

## Cài đặt

Yêu cầu Python ≥ 3.9.

```bash
git clone <repo-url>
cd nao-coding-agent
pip install -e .            # core — đủ để chạy MCP server qua stdio (local)
pip install -e ".[all]"     # + chế độ CLI (OpenAI) + HTTP/legacy + HF Space
```

Sau khi cài, bạn có sẵn lệnh `nao-agent` trong PATH (do `pyproject.toml`
khai báo `[project.scripts]`).

## Bắt đầu trong 60 giây

Ý tưởng chung cho mọi client: trỏ `command` tới `nao-agent`, truyền
`--workdir <đường-dẫn-project>` rồi `serve`. Xong.

### Claude Desktop

Thêm vào `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nao-coding-agent": {
      "command": "nao-agent",
      "args": ["--workdir", "/duong/dan/toi/project", "serve"]
    }
  }
}
```

Khởi động lại Claude Desktop — vào chat, bạn sẽ thấy tool `list_files`,
`edit_file`, `exec_terminal`... xuất hiện trong danh sách tool khả dụng.

### Cursor

Thêm vào `.cursor/mcp.json` (theo project) hoặc `~/.cursor/mcp.json`
(toàn cục):

```json
{
  "mcpServers": {
    "nao-coding-agent": {
      "command": "nao-agent",
      "args": ["--workdir", "/duong/dan/toi/project", "serve"]
    }
  }
}
```

### VS Code (Copilot Chat / MCP)

Thêm vào `settings.json`:

```json
{
  "mcp.servers": {
    "nao-coding-agent": {
      "command": "nao-agent",
      "args": ["--workdir", "${workspaceFolder}", "serve"]
    }
  }
}
```

### Codex CLI / client MCP khác

Bất kỳ client nào hỗ trợ MCP transport `stdio` đều dùng được — chỉ cần
trỏ `command` tới `nao-agent` (hoặc `python -m nao_agent`) với
`args: ["serve"]`.

Không truyền `--workdir` thì mặc định là thư mục hiện tại lúc client spawn
tiến trình (hoặc đặt biến môi trường `AGENT_WORKDIR`).

## Cách dùng hằng ngày

Sau khi nối dây xong, cứ nói chuyện với AI như bình thường — nó sẽ tự gọi
tool khi cần:

> "Đọc file `app/config.py`, tìm hàm `load_settings`, sửa để nó đọc thêm
> biến môi trường `REDIS_URL`."

AI sẽ tự: `read_file` → `find_function("load_settings")` để lấy đúng
source nguyên văn → `edit_file` để patch → chạy `py_compile`/test qua
`exec_terminal` để xác nhận không vỡ cú pháp → `complete_task` khi xong.

Vài ví dụ prompt khác:

- *"Chạy `pytest`, xem test nào fail rồi sửa."*
- *"Tạo file `utils/slugify.py` mới với 1 hàm `slugify(text)`."*
- *"Đăng ký secret `GITHUB_TOKEN` trỏ tới `~/.secrets/github_token`, rồi
  dùng nó để `git push` lên remote `origin`."*
- *"Đặt biến môi trường `NODE_ENV=production` rồi chạy `npm run build`."*

## Danh sách tool đầy đủ

| Tool | Việc | Ghi chú |
|---|---|---|
| `list_files` | Liệt kê cây thư mục project | Bỏ qua `.git`, `node_modules`, `__pycache__` |
| `read_file` | Đọc nội dung file (toàn bộ hoặc theo khoảng dòng) | |
| `find_function` | Tìm chính xác 1 hàm/class/method Python bằng AST | Trả về source nguyên văn — dùng thẳng làm `old_str` |
| `write_file` | **Chỉ** tạo file mới | Từ chối nếu path đã tồn tại — [xem chi tiết](#ghi-file-chỉ-tạo-mới--sửa--xóa--không-có-đường-ghi-đè) |
| `edit_file` | Patch `old_str` → `new_str` trong file đã có | Bắt buộc khớp chính xác, duy nhất |
| `delete_file` | Xóa 1 file | |
| `exec_terminal` | Chạy lệnh shell trong `WORKDIR` | Hỗ trợ `env`, `secrets` — [xem chi tiết](#terminal-mạnh-như-1-người-dùng-thật) |
| `set_env` / `unset_env` / `list_env` | Biến môi trường persistent (`export`) | Chỉ dùng cho cấu hình không nhạy cảm |
| `register_secret` / `list_secrets` / `forget_secret` | Quản lý secret theo tên | [Xem chi tiết](#secret-theo-tên--dùng-tokenapi-key-mà-ai-không-bao-giờ-thấy-giá-trị-thật) |
| `complete_task` | Báo hiệu đã xong nhiệm vụ | AI luôn gọi tool này khi kết thúc |

Bật thêm bằng `HF_SPACE_MODE=1`: `push_to_space`, `restart_space`,
`refresh_context` — xem [Hugging Face Space mode](#3-hugging-face-space-mode).

## Ghi file: chỉ tạo mới / sửa / xóa — không có đường ghi đè

`write_file` **chỉ tạo file chưa tồn tại**. Không có tham số, cờ, hay tool
"confirmed" nào cho phép ghi đè toàn bộ nội dung 1 file đã có — kể cả nếu
AI cố tình yêu cầu. Muốn thay đổi 1 file đã có, chỉ có 2 đường:

- **Sửa 1 phần** → `edit_file(path, old_str, new_str)`. Kết hợp với
  `find_function` để lấy đúng `old_str` nguyên văn, tránh lỗi khớp chuỗi.
- **Viết lại toàn bộ** → `delete_file(path)` rồi `write_file(path, ...)` —
  2 bước tách biệt có chủ ý, để AI không bao giờ vô tình "patch nhầm" mà
  xóa sạch code cũ trong 1 lần gọi.

Mỗi lần `write_file`/`edit_file` một file `.py`, tool tự chạy
`py_compile` và báo ngay nếu có lỗi cú pháp — sửa sai được phát hiện
trước khi bạn kịp `git diff`.

## Secret theo tên — dùng token/API key mà AI không bao giờ thấy giá trị thật

Đừng bao giờ dán token thật vào chat với AI. Thay vào đó:

**Bước 1 — lưu secret trong 1 file, ở bất kỳ đâu trên máy bạn** (không
cần nằm trong project):

```bash
mkdir -p ~/.secrets && echo -n "ghp_xxxxxxxxxxxx" > ~/.secrets/github_token
chmod 600 ~/.secrets/github_token
```

**Bước 2 — đăng ký secret 1 lần** (chỉ nói với AI, hoặc gọi thẳng tool):

```
register_secret(name="GITHUB_TOKEN", path="~/.secrets/github_token")
```

Tool chỉ lưu **đường dẫn** vào `~/.nao_agent/secrets.json` (`chmod 600`),
**không bao giờ** đọc hay in giá trị bên trong ra kết quả trả về.

**Bước 3 — dùng lại bằng tên** trong bất kỳ lệnh terminal nào:

```
exec_terminal(
  command="git push https://$GITHUB_TOKEN@github.com/you/repo.git main",
  secrets=["GITHUB_TOKEN"]
)
```

Điều gì xảy ra phía sau:

1. Giá trị thật chỉ được đọc từ đĩa **ngay lúc chạy lệnh này**, bơm thẳng
   vào biến môi trường của tiến trình con — không đi qua bất kỳ tin nhắn
   hay log nào.
2. Output (`stdout`/`stderr`) được quét lại trước khi trả về cho AI: nếu
   giá trị thật vô tình bị in ra, nó tự động bị thay bằng
   `***REDACTED:GITHUB_TOKEN***`.
3. `list_secrets()` chỉ trả về `tên -> đường dẫn`, không bao giờ trả về
   nội dung file. `forget_secret(name)` gỡ đăng ký (không đụng file gốc).

> Muốn đổi vị trí file mapping mặc định (`~/.nao_agent/secrets.json`)?
> Đặt `AGENT_SECRETS_FILE=/duong/dan/khac.json`.

Biến môi trường **không nhạy cảm** (`NODE_ENV`, `PORT`, `DATABASE_HOST`...)
thì không cần cơ chế secret — dùng `set_env(key, value)` (persistent, áp
dụng cho mọi `exec_terminal` sau đó) hoặc tham số `env={...}` ngay trong
`exec_terminal` (chỉ áp dụng cho đúng 1 lệnh).

## Terminal: mạnh như 1 người dùng thật

`exec_terminal` chạy đúng với quyền của tài khoản đã khởi động
`nao-agent` — như bạn tự gõ lệnh vào terminal của mình:

```
exec_terminal(command="npm install && npm run build", env={"NODE_ENV": "production"})
exec_terminal(command="git log --oneline -5")
exec_terminal(command="curl -s https://api.example.com/health")
```

Không có blocklist theo từ khóa kiểu "cấm `sudo`, cấm `git push`" — nếu
tài khoản của bạn có quyền `sudo`, AI cũng dùng được, giống hệt bạn tự gõ.
Lớp chặn **duy nhất** còn lại là nhóm lệnh **phá hủy không thể hoàn tác ở
cấp cả hệ thống** (không chỉ trong project): `rm -rf /`, fork bomb, `mkfs`,
ghi trực tiếp vào `/dev/sda`... Đây là những lệnh mà một lần AI gõ nhầm là
không có đường lùi, khác hẳn các thao tác dev bình thường dù có "nguy
hiểm" tới đâu. Muốn tắt hẳn cả lớp chặn này (full quyền tuyệt đối, không
giới hạn gì): đặt `AGENT_ALLOW_DESTRUCTIVE=1` lúc khởi động agent.

## Chế độ nâng cao

### 1. CLI 1 phát (không cần client MCP)

Tự gọi thẳng OpenAI API (function calling), không cần Claude Desktop/
Cursor gì cả — kiểu Aider/Codex CLI:

```bash
pip install -e ".[cli]"
export OPENAI_API_KEY=sk-...
nao-agent --workdir /duong/dan/toi/project task "Sửa lỗi ở hàm parse_config trong config.py"
```

Model mặc định đặt trong `nao_agent/cli_agent.py` (`DEFAULT_MODEL`), đổi
bằng `--model` hoặc biến môi trường `OPENAI_MODEL`.

### 2. HTTP / legacy (deploy remote)

Dựng lại kiểu MCP-over-HTTP + REST API trần (`curl`) + GitHub OAuth, để
vẫn deploy được lên server thật (vd Hugging Face Space):

```bash
pip install -e ".[http]"
nao-agent serve --http --host 0.0.0.0 --port 7860
```

Cần `MCP_SECRET_TOKEN` (Bearer token) **hoặc** bộ 4 biến
`GITHUB_CLIENT_ID` + `GITHUB_CLIENT_SECRET` + `ALLOWED_GITHUB_USERNAME` +
`MCP_PUBLIC_BASE_URL` để bật GitHub OAuth. Thiếu cả 2 → server **fail-
closed**, từ chối mọi request thay vì mở toang.

Endpoint MCP: `/mcp-server/mcp`. REST trần:

```bash
curl -H "Authorization: Bearer $MCP_SECRET_TOKEN" http://localhost:7860/api/tools

curl -X POST -H "Authorization: Bearer $MCP_SECRET_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool": "list_files", "args": {"path": "."}}' \
  http://localhost:7860/api/call
```

### 3. Hugging Face Space mode

Điều khiển 1 Hugging Face Space **từ xa** (kéo code về, sửa, push, restart,
giám sát sức khỏe qua Telegram) — dành cho ai vẫn muốn dùng kiểu cũ:

```bash
pip install -e ".[space]"
export HF_SPACE_MODE=1
export TARGET_SPACE_ID=<user>/<space>
export HF_TOKEN=hf_xxx
# tuỳ chọn — báo lỗi + nhận lệnh qua Telegram
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
nao-agent serve
```

Bật cờ này sẽ tự kéo code Space mục tiêu về `WORKDIR` lúc khởi động, cài
`requirements.txt` của Space đó, và thêm 3 tool `push_to_space` /
`restart_space` / `refresh_context`.

## Biến môi trường — tra cứu nhanh

| Biến | Dùng cho | Mặc định |
|---|---|---|
| `AGENT_WORKDIR` | Thư mục làm việc | thư mục hiện tại |
| `AGENT_SECRETS_FILE` | File mapping tên secret → đường dẫn | `~/.nao_agent/secrets.json` |
| `AGENT_ALLOW_DESTRUCTIVE` | Tắt lớp chặn lệnh hủy diệt cấp hệ thống | tắt (vẫn chặn) |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Chế độ CLI (`nao-agent task`) | — |
| `MCP_SECRET_TOKEN` | Bearer token cho chế độ `--http` | — |
| `GITHUB_CLIENT_ID/SECRET`, `ALLOWED_GITHUB_USERNAME`, `MCP_PUBLIC_BASE_URL` | GitHub OAuth cho `--http` | — |
| `HF_SPACE_MODE`, `TARGET_SPACE_ID`, `HF_TOKEN` | Chế độ Hugging Face Space | tắt |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Báo lỗi/nhận lệnh qua Telegram (HF Space mode) | tắt |

## Kiến trúc

```
                 ┌─────────────────────────────┐
 Claude Desktop  │                             │
 Cursor          │   nao-agent (subprocess)    │
 VS Code Copilot ├──────────► stdio ◄──────────┤
 Codex CLI       │                             │
                 │  ┌───────────────────────┐  │
                 │  │ mcp_server.py         │  │   đăng ký tool lên FastMCP
                 │  ├───────────────────────┤  │
                 │  │ core.py               │  │   list/read/find/write/edit/
                 │  │  (file ops + terminal)│  │   delete/exec_terminal/env
                 │  ├───────────────────────┤  │
                 │  │ secrets_manager.py    │  │   name -> path, resolve
                 │  │  (secret theo tên)    │  │   lúc chạy, redact output
                 │  ├───────────────────────┤  │
                 │  │ cli_agent.py          │  │   chế độ CLI gọi OpenAI
                 │  ├───────────────────────┤  │
                 │  │ space_ops.py          │  │   HF Space mode (tùy chọn)
                 │  └───────────────────────┘  │
                 └──────────────┬──────────────┘
                                │ subprocess / filesystem
                                ▼
                     Thư mục project của BẠN
                        (chỉ trong WORKDIR)
```

Mọi thao tác file đều đi qua `_safe_path()` — chặn cứng mọi path muốn
thoát ra ngoài `WORKDIR` (kiểu `../../etc/passwd`).

## An toàn & mô hình tin cậy

nao-coding-agent **không phải sandbox**. Nó chạy với **đúng quyền của tài
khoản đã khởi động nó**, giống hệt việc bạn tự mở terminal gõ lệnh — đây
là lựa chọn thiết kế có chủ ý (giống Claude Code, Cursor Agent, Aider),
không phải sơ suất. Vài rào chắn cụ thể còn lại:

- **Không thoát khỏi `WORKDIR`** — mọi tool file dùng `_safe_path()`.
- **Không ghi đè file đã có** — chỉ tạo mới/sửa/xóa (xem [mục trên](#ghi-file-chỉ-tạo-mới--sửa--xóa--không-có-đường-ghi-đè)).
- **Secret không lộ qua chat/log** — đăng ký theo tên, resolve lúc chạy,
  tự động redact output (xem [mục trên](#secret-theo-tên--dùng-tokenapi-key-mà-ai-không-bao-giờ-thấy-giá-trị-thật)).
- **Chỉ chặn nhóm lệnh phá hủy cấp hệ thống, không thể hoàn tác** trong
  `exec_terminal`, tắt được bằng `AGENT_ALLOW_DESTRUCTIVE=1`.
- **Chế độ `--http` public fail-closed**: thiếu `MCP_SECRET_TOKEN`/OAuth
  là từ chối hết, không có chuyện "quên cấu hình = mở toang".

**Khuyến nghị:** chỉ trỏ `--workdir` vào đúng project bạn thật sự muốn AI
thao tác — không trỏ vào `$HOME` hay ổ đĩa gốc. Với secret thật, luôn đi
qua `register_secret`, không bao giờ dán trực tiếp vào chat.

## Câu hỏi thường gặp

**Q: Có gửi code của tôi lên server nào của Anthropic/OpenAI/nhà phát
triển tool này không?**
A: Không. `nao-agent` chỉ là 1 tiến trình con nói chuyện qua stdio với
đúng client AI bạn đang chạy trên máy bạn. Ở chế độ mặc định, không có kết
nối mạng nào do chính tool này khởi tạo (trừ khi bạn tự bảo AI chạy
`curl`/`git push`... qua `exec_terminal`, hoặc bật các chế độ nâng cao ở
trên).

**Q: AI có thể xóa nhầm hết code của tôi không?**
A: `write_file` không thể ghi đè file đã có, và `delete_file` chỉ xóa
đúng 1 file được chỉ định — không có tool nào xóa cả thư mục. Nên dùng
kèm Git: `commit` trước khi giao việc lớn cho AI vẫn là thói quen tốt
nhất, tool này không thay thế version control.

**Q: Vì sao không sandbox hẳn bằng container/VM?**
A: Có thể tự làm — chạy `nao-agent` trong Docker/VM trỏ `--workdir` vào
volume mount là cách đơn giản nhất nếu bạn cần cách ly hoàn toàn. Mặc
định tool nhắm tới trải nghiệm "chạy ngay trên máy dev của bạn", giống
Claude Code/Cursor Agent, nên không tự đóng gói sandbox riêng.

## Đóng góp

PR/issue đều được chào đón — đặc biệt là:

- Thêm hỗ trợ ngôn ngữ khác ngoài Python cho `find_function` (hiện dùng
  `ast`, chỉ hiểu Python).
- Thêm client MCP mới vào phần hướng dẫn cài đặt.
- Cải thiện cơ chế redact secret (vd secret nhiều dòng, secret dạng JSON).

```bash
git clone <repo-url>
cd nao-coding-agent
pip install -e ".[all]"
python -m py_compile nao_agent/*.py   # kiểm tra nhanh trước khi mở PR
```

## Giấy phép

MIT — xem [`LICENSE`](LICENSE).

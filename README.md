# 🐧 nao-coding-agent

**Turn any AI (Claude, Cursor, Copilot, Codex CLI...) into a coding agent
that runs 100% LOCALLY on your machine** — reading files, editing code,
deleting files, and running terminal commands like a real developer, with
no remote server, no `curl`, no token, and nothing of your code ever
leaving your machine except through the exact AI client you're already
using.

> Runs over the **MCP** (Model Context Protocol) `stdio` transport: your
> AI client spawns `nao-agent` as a subprocess and talks to it over
> stdin/stdout. Wire it up once, use it forever.

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/protocol-MCP-purple.svg)](https://modelcontextprotocol.io)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

*[Tiếng Việt](README.vi.md)*

---

## Table of contents

- [Why this project exists](#why-this-project-exists)
- [Highlights](#highlights)
- [Installation](#installation)
- [Get started in 60 seconds](#get-started-in-60-seconds)
  - [Claude Desktop](#claude-desktop)
  - [Cursor](#cursor)
  - [VS Code (Copilot Chat / MCP)](#vs-code-copilot-chat--mcp)
  - [Codex CLI / any other MCP client](#codex-cli--any-other-mcp-client)
- [Everyday usage](#everyday-usage)
- [Full tool reference](#full-tool-reference)
- [File writes: create / edit / delete only — no overwrite path](#file-writes-create--edit--delete-only--no-overwrite-path)
- [Named secrets — let the AI use tokens/API keys without ever seeing the real value](#named-secrets--let-the-ai-use-tokensapi-keys-without-ever-seeing-the-real-value)
- [Terminal: as powerful as a real user](#terminal-as-powerful-as-a-real-user)
- [Advanced modes](#advanced-modes)
  - [1. Standalone CLI (no MCP client needed)](#1-standalone-cli-no-mcp-client-needed)
  - [2. HTTP / legacy (remote deploy)](#2-http--legacy-remote-deploy)
  - [3. Hugging Face Space mode](#3-hugging-face-space-mode)
- [Environment variables — quick reference](#environment-variables--quick-reference)
- [Architecture](#architecture)
- [Safety & trust model](#safety--trust-model)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)

---

## Why this project exists

Most "AI coding agents" today force you into a trade-off you'd rather not
make:

1. **Upload your code to some SaaS dashboard** so the AI can read your
   folder, or
2. Stand up your own server, wire up tokens, and deploy it somewhere just
   so your local AI can reach into your own machine.

**nao-coding-agent skips both.** It's a small MCP process that runs right
on your machine, spawned as a subprocess by the AI client you already use
(Claude Desktop, Cursor, VS Code, Codex CLI...). No network hop, no
cloud, no third party sitting between you and your AI — install it and
it just works, the same way `git` or `npm` already do.

The design philosophy throughout: **give the AI enough power to be
genuinely useful (read/edit/delete files, run a real terminal), while
keeping a handful of minimal, explicit guardrails, with no shortcut
around them**, precisely at the points where a single AI mistake would
be unrecoverable (overwriting lost code, wrecking the whole system,
leaking a secret).

## Highlights

| | |
|---|---|
| 🔌 **Zero-config, zero-server** | No HTTP, no token, no deployment — just one line in the MCP client config you already have. |
| 🧠 **Works with any MCP client** | Claude Desktop, Cursor, VS Code Copilot Chat, Codex CLI, or anything that speaks `stdio`. |
| 📝 **Safe file editing** | `write_file` only creates new files — **there is no way to overwrite an existing file**. Changing code always goes through `edit_file` (targeted patch) or `find_function` (exact AST-based location). |
| 🔐 **Named secrets, values never exposed** | Store tokens/API keys/passwords in any file, anywhere on your disk, register them once by name — the AI can use them in terminal commands without **ever seeing the real value**, even in logs. |
| 🖥️ **A terminal that behaves like a real user** | Set environment variables (per-call or persistent), run `git`, `ssh`, `curl`, install packages... The only thing blocked is the class of destructive, unrecoverable, whole-system commands. |
| 🌲 **Pinpoint code location via AST** | `find_function` locates the exact function/class/method in a Python file and returns the verbatim source, ready to use as `old_str` for `edit_file` — no more "AI guessing line numbers." |
| 🧩 **Extensible** | A standalone CLI mode that calls OpenAI directly, a legacy HTTP/REST mode for remote deployment, and a mode for remotely operating a Hugging Face Space (with Telegram monitoring) — all optional, all off by default. |

## Installation

Requires Python ≥ 3.9.

```bash
git clone <repo-url>
cd nao-coding-agent
pip install -e .            # core — enough to run the MCP server over stdio (local)
pip install -e ".[all]"     # + CLI mode (OpenAI) + HTTP/legacy + HF Space
```

Once installed, the `nao-agent` command is available on your PATH (declared
in `pyproject.toml` under `[project.scripts]`).

## Get started in 60 seconds

The general idea for every client: point `command` at `nao-agent`, pass
`--workdir <path-to-your-project>` and `serve`. That's it.

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "nao-coding-agent": {
      "command": "nao-agent",
      "args": ["--workdir", "/path/to/your/project", "serve"]
    }
  }
}
```

Restart Claude Desktop — in a new chat you'll see tools like `list_files`,
`edit_file`, `exec_terminal`... show up in the available tools list.

### Cursor

Add to `.cursor/mcp.json` (per-project) or `~/.cursor/mcp.json` (global):

```json
{
  "mcpServers": {
    "nao-coding-agent": {
      "command": "nao-agent",
      "args": ["--workdir", "/path/to/your/project", "serve"]
    }
  }
}
```

### VS Code (Copilot Chat / MCP)

Add to `settings.json`:

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

### Codex CLI / any other MCP client

Any client that supports the `stdio` MCP transport works — just point
`command` at `nao-agent` (or `python -m nao_agent`) with
`args: ["serve"]`.

If you don't pass `--workdir`, it defaults to the current directory at
the moment the client spawns the process (or set the `AGENT_WORKDIR`
environment variable).

## Everyday usage

Once it's wired up, just talk to your AI normally — it calls the tools
whenever it needs to:

> "Read `app/config.py`, find the `load_settings` function, and update it
> to also read the `REDIS_URL` environment variable."

The AI will typically: `read_file` → `find_function("load_settings")` to
get the exact verbatim source → `edit_file` to patch it → run
`py_compile`/tests via `exec_terminal` to confirm nothing broke →
`complete_task` when it's done.

A few more example prompts:

- *"Run `pytest`, see which tests fail, and fix them."*
- *"Create a new file `utils/slugify.py` with a `slugify(text)` function."*
- *"Register the secret `GITHUB_TOKEN` pointing at `~/.secrets/github_token`,
  then use it to `git push` to the `origin` remote."*
- *"Set `NODE_ENV=production` and run `npm run build`."*

## Full tool reference

| Tool | What it does | Notes |
|---|---|---|
| `list_files` | List the project's directory tree | Skips `.git`, `node_modules`, `__pycache__` |
| `read_file` | Read a file's contents (whole file or a line range) | |
| `find_function` | Find the exact source of a Python function/class/method via AST | Returns the verbatim source — use it directly as `old_str` |
| `write_file` | **Only** creates new files | Refuses if the path already exists — [see below](#file-writes-create--edit--delete-only--no-overwrite-path) |
| `edit_file` | Patch `old_str` → `new_str` in an existing file | Must match exactly and uniquely |
| `delete_file` | Delete a single file | |
| `exec_terminal` | Run a shell command inside `WORKDIR` | Supports `env`, `secrets` — [see below](#terminal-as-powerful-as-a-real-user) |
| `set_env` / `unset_env` / `list_env` | Persistent environment variables (`export`) | For non-sensitive config only |
| `register_secret` / `list_secrets` / `forget_secret` | Manage named secrets | [See below](#named-secrets--let-the-ai-use-tokensapi-keys-without-ever-seeing-the-real-value) |
| `complete_task` | Signal that the task is done | The AI always calls this when it's finished |

Enabled by `HF_SPACE_MODE=1`: `push_to_space`, `restart_space`,
`refresh_context` — see [Hugging Face Space mode](#3-hugging-face-space-mode).

## File writes: create / edit / delete only — no overwrite path

`write_file` **only creates files that don't exist yet**. There is no
parameter, flag, or "confirmed" tool that lets it overwrite an existing
file's contents — not even if the AI explicitly asks. To change an
existing file, there are only two paths:

- **Partial change** → `edit_file(path, old_str, new_str)`. Pair it with
  `find_function` to get the exact verbatim `old_str` and avoid string-
  matching mistakes.
- **Full rewrite** → `delete_file(path)` then `write_file(path, ...)` —
  two deliberately separate steps, so the AI can never accidentally wipe
  out existing code with a single "patch" call.

Every time `write_file`/`edit_file` touches a `.py` file, the tool runs
`py_compile` automatically and reports any syntax error immediately —
mistakes get caught before you even run `git diff`.

## Named secrets — let the AI use tokens/API keys without ever seeing the real value

Never paste a real token directly into a chat with the AI. Instead:

**Step 1 — store the secret in a file, anywhere on your machine**
(it doesn't need to live inside the project):

```bash
mkdir -p ~/.secrets && echo -n "ghp_xxxxxxxxxxxx" > ~/.secrets/github_token
chmod 600 ~/.secrets/github_token
```

**Step 2 — register it once** (just tell the AI, or call the tool
directly):

```
register_secret(name="GITHUB_TOKEN", path="~/.secrets/github_token")
```

The tool only stores the **path** in `~/.nao_agent/secrets.json`
(`chmod 600`) — it **never** reads or prints the file's contents in its
result.

**Step 3 — reuse it by name** in any terminal command:

```
exec_terminal(
  command="git push https://$GITHUB_TOKEN@github.com/you/repo.git main",
  secrets=["GITHUB_TOKEN"]
)
```

What happens under the hood:

1. The real value is only read from disk **at the moment this command
   runs**, injected straight into the child process's environment — it
   never passes through any message or log.
2. The output (`stdout`/`stderr`) is scanned before being returned to the
   AI: if the real value accidentally shows up in it, it's automatically
   replaced with `***REDACTED:GITHUB_TOKEN***`.
3. `list_secrets()` only returns `name -> path`, never the file's
   contents. `forget_secret(name)` removes the registration (the
   underlying file is untouched).

> Want to change the default mapping-file location
> (`~/.nao_agent/secrets.json`)? Set
> `AGENT_SECRETS_FILE=/some/other/path.json`.

For **non-sensitive** environment variables (`NODE_ENV`, `PORT`,
`DATABASE_HOST`...) you don't need the secrets mechanism — use
`set_env(key, value)` (persistent, applies to every `exec_terminal`
call afterward) or the `env={...}` parameter directly on `exec_terminal`
(applies to just that one call).

## Terminal: as powerful as a real user

`exec_terminal` runs with exactly the permissions of the account that
started `nao-agent` — as if you typed the command into your own terminal:

```
exec_terminal(command="npm install && npm run build", env={"NODE_ENV": "production"})
exec_terminal(command="git log --oneline -5")
exec_terminal(command="curl -s https://api.example.com/health")
```

There's no keyword blocklist like "block `sudo`, block `git push`" — if
your account has `sudo` rights, the AI can use them too, same as if you
typed it yourself. The **only** remaining guard is a small set of
**destructive, unrecoverable, whole-system commands** (not just
project-scoped ones): `rm -rf /`, fork bombs, `mkfs`, writing directly to
`/dev/sda`... These are commands where a single mistaken invocation has
no way back, unlike ordinary dev operations no matter how "risky" they
look. To disable even this last guard (full, unrestricted power): set
`AGENT_ALLOW_DESTRUCTIVE=1` when starting the agent.

## Advanced modes

### 1. Standalone CLI (no MCP client needed)

Calls the OpenAI API directly (function calling) — no Claude Desktop/
Cursor required, Aider/Codex-CLI style:

```bash
pip install -e ".[cli]"
export OPENAI_API_KEY=sk-...
nao-agent --workdir /path/to/your/project task "Fix the bug in parse_config in config.py"
```

The default model is set in `nao_agent/cli_agent.py` (`DEFAULT_MODEL`),
override it with `--model` or the `OPENAI_MODEL` environment variable.

### 2. HTTP / legacy (remote deploy)

Rebuilds a classic MCP-over-HTTP + plain REST API (`curl`) + GitHub OAuth
setup, so you can still deploy to a real server (e.g. a Hugging Face
Space):

```bash
pip install -e ".[http]"
nao-agent serve --http --host 0.0.0.0 --port 7860
```

Requires either `MCP_SECRET_TOKEN` (Bearer token) **or** all four of
`GITHUB_CLIENT_ID` + `GITHUB_CLIENT_SECRET` + `ALLOWED_GITHUB_USERNAME` +
`MCP_PUBLIC_BASE_URL` to enable GitHub OAuth. Missing both → the server
**fails closed** and rejects every request instead of opening wide.

MCP endpoint: `/mcp-server/mcp`. Plain REST:

```bash
curl -H "Authorization: Bearer $MCP_SECRET_TOKEN" http://localhost:7860/api/tools

curl -X POST -H "Authorization: Bearer $MCP_SECRET_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"tool": "list_files", "args": {"path": "."}}' \
  http://localhost:7860/api/call
```

### 3. Hugging Face Space mode

Remotely operate a Hugging Face Space (pull its code, edit it, push,
restart, monitor health via Telegram) — for anyone who still wants the
original remote-control workflow:

```bash
pip install -e ".[space]"
export HF_SPACE_MODE=1
export TARGET_SPACE_ID=<user>/<space>
export HF_TOKEN=hf_xxx
# optional — get error alerts + send commands via Telegram
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
nao-agent serve
```

Enabling this flag automatically pulls the target Space's code into
`WORKDIR` at startup, best-effort installs its `requirements.txt`, and
adds three tools: `push_to_space`, `restart_space`, `refresh_context`.

## Environment variables — quick reference

| Variable | Used for | Default |
|---|---|---|
| `AGENT_WORKDIR` | Working directory | current directory |
| `AGENT_SECRETS_FILE` | Secret name → path mapping file | `~/.nao_agent/secrets.json` |
| `AGENT_ALLOW_DESTRUCTIVE` | Disables the system-level destructive-command guard | off (still guarded) |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Standalone CLI mode (`nao-agent task`) | — |
| `MCP_SECRET_TOKEN` | Bearer token for `--http` mode | — |
| `GITHUB_CLIENT_ID/SECRET`, `ALLOWED_GITHUB_USERNAME`, `MCP_PUBLIC_BASE_URL` | GitHub OAuth for `--http` | — |
| `HF_SPACE_MODE`, `TARGET_SPACE_ID`, `HF_TOKEN` | Hugging Face Space mode | off |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Error alerts / commands via Telegram (HF Space mode) | off |

## Architecture

```
                 ┌─────────────────────────────┐
 Claude Desktop  │                             │
 Cursor          │   nao-agent (subprocess)    │
 VS Code Copilot ├──────────► stdio ◄──────────┤
 Codex CLI       │                             │
                 │  ┌───────────────────────┐  │
                 │  │ mcp_server.py         │  │   registers tools on FastMCP
                 │  ├───────────────────────┤  │
                 │  │ core.py               │  │   list/read/find/write/edit/
                 │  │  (file ops + terminal)│  │   delete/exec_terminal/env
                 │  ├───────────────────────┤  │
                 │  │ secrets_manager.py    │  │   name -> path, resolved at
                 │  │  (named secrets)      │  │   call time, output redacted
                 │  ├───────────────────────┤  │
                 │  │ cli_agent.py          │  │   standalone CLI (OpenAI)
                 │  ├───────────────────────┤  │
                 │  │ space_ops.py          │  │   HF Space mode (optional)
                 │  └───────────────────────┘  │
                 └──────────────┬──────────────┘
                                │ subprocess / filesystem
                                ▼
                       YOUR project folder
                        (WORKDIR only)
```

Every file operation goes through `_safe_path()`, which hard-blocks any
path attempting to escape `WORKDIR` (e.g. `../../etc/passwd`).

## Safety & trust model

nao-coding-agent is **not a sandbox**. It runs with **exactly the
permissions of the account that started it** — the same as opening your
own terminal and typing the command yourself. That's a deliberate design
choice (the same one Claude Code, Cursor Agent, and Aider make), not an
oversight. The concrete guardrails that remain:

- **Can't escape `WORKDIR`** — every file tool goes through `_safe_path()`.
- **Can't overwrite an existing file** — only create/edit/delete (see
  [above](#file-writes-create--edit--delete-only--no-overwrite-path)).
- **Secrets never pass through chat/logs** — registered by name, resolved
  at call time, output auto-redacted (see
  [above](#named-secrets--let-the-ai-use-tokensapi-keys-without-ever-seeing-the-real-value)).
- **`exec_terminal` only blocks the class of unrecoverable, system-level
  destructive commands**, and even that can be turned off with
  `AGENT_ALLOW_DESTRUCTIVE=1`.
- **Public `--http` mode fails closed**: missing `MCP_SECRET_TOKEN`/OAuth
  means every request is rejected — there's no "forgot to configure it =
  wide open" failure mode.

**Recommendation:** only point `--workdir` at the exact project you want
the AI to work on — not at `$HOME` or a root filesystem. For real
secrets, always go through `register_secret`; never paste them directly
into chat.

## FAQ

**Q: Does my code get sent to any server run by Anthropic/OpenAI/this
tool's maintainer?**
A: No. `nao-agent` is just a subprocess talking over stdio to whichever
AI client you're already running locally. In the default mode, this tool
itself never opens a network connection (unless you ask the AI to run
`curl`/`git push`/etc. via `exec_terminal`, or you enable one of the
advanced modes above).

**Q: Could the AI accidentally delete all my code?**
A: `write_file` can never overwrite an existing file, and `delete_file`
only removes the single file it's told to — there's no tool that deletes
an entire directory. Using it alongside Git is still good practice:
commit before handing off a big task to the AI. This tool doesn't replace
version control.

**Q: Why not sandbox it fully with a container/VM?**
A: You can — running `nao-agent` inside Docker/a VM with `--workdir`
pointed at a mounted volume is the simplest way to get full isolation if
you need it. By default the tool aims for a "runs right on your own dev
machine" experience, the same way Claude Code/Cursor Agent do, so it
doesn't bundle its own sandbox.

## Contributing

PRs and issues are welcome — especially:

- Adding non-Python language support to `find_function` (it currently
  uses Python's `ast` module, so it only understands Python).
- Adding new MCP client setup instructions.
- Improving secret redaction (e.g. multi-line secrets, JSON-shaped
  secrets).

```bash
git clone <repo-url>
cd nao-coding-agent
pip install -e ".[all]"
python -m py_compile nao_agent/*.py   # quick sanity check before opening a PR
```

## License

MIT — see [`LICENSE`](LICENSE).

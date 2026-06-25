# Apek — Coding Agent

**Apek** is an interactive, terminal-based AI coding assistant. It holds a conversation in your terminal, calls an LLM to reason about your request, and executes filesystem and shell operations to create, edit, and manage real code projects — all confined to a sandboxed projects directory for safety.

---

## Preview

<img src="./public/preview.png" alt="preview_terminal">

---

## Features

- **Interactive chat loop** — a continuous conversation with an AI coding agent.
- **Tool-driven actions** — the agent can `read_file`, `list_files`, `edit_file`, `create_directory`, and `execute_command` to do real work.
- **Sandboxed filesystem** — all file operations are restricted to a configurable projects root; `../` escapes and absolute paths outside the root are blocked.
- **Safety rules** — no destructive commands (e.g. `rm`) without explicit user permission; the agent writes code but never starts dev servers.
- **Rich terminal UI** — built with React + Ink, showing thinking state, messages, and formatted tool calls/results.
- **Detailed debug logging** — every run writes a timestamped trace (user inputs, model responses, tool calls/results, and masked API traces) to `error-logs/`.

---

## How It Works

The terminal UI (`ui/src/App.tsx`, React + Ink) spawns the Python backend (`agent.py`). User input flows to the backend, which builds a system prompt, calls the **Ollama API**, parses tool calls out of the model's response, dispatches them, and loops until the task is complete. Every session is traced to `error-logs/` for debugging.

| File / Dir       | Role                                              |
| ---------------- | ------------------------------------------------- |
| `agent.py`       | Entry point                                       |
| `agent_loop.py`  | Main conversation loop and tool dispatch          |
| `llm_client.py`  | HTTP client for the Ollama API                    |
| `tools.py`       | Filesystem/shell tools and sandbox enforcement    |
| `parsing.py`     | Extracts tool calls from LLM output               |
| `prompts.py`     | System prompt construction                        |
| `config.py`      | Environment configuration                         |
| `run_logger.py`  | Writes debug trace files                          |
| `ui/`            | Ink-based React terminal UI                       |

**Tech stack:** Python 3.10+ (standard library only) for the backend, React 19 + Ink + TypeScript (run via `tsx`) for the UI, and an Ollama-compatible LLM (e.g. Qwen3-Coder).

---

## Prerequisites

| Requirement    | Version                                          |
| -------------- | ------------------------------------------------ |
| Python         | 3.10+                                            |
| Node.js + npm  | 18+                                              |
| Ollama API Key | [Get one here](https://ollama.com/settings/keys) |

---

## Setup

### 1. Navigate to the project root

```bash
cd apex
```

---

### 2. Configure environment variables

**Linux / macOS**

```bash
cp .env.example .env
```

**Windows (PowerShell)**

```powershell
Copy-Item .env.example .env
```

Then open `.env` and fill in your values:

```env
OLLAMA_BASE_URL=https://ollama.com/api
OLLAMA_CHAT_PATH=/chat
OLLAMA_API_KEY=your_api_key_here
OLLAMA_MODEL=qwen3-coder-next
```

---

### 3. Create and activate a virtual environment

**Linux / macOS**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell)**

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (CMD)**

```bat
py -m venv venv
venv\Scripts\activate.bat
```

---

### 4. Install UI dependencies

```bash
cd ui
npm install
cd ..
```

---

## Running the App

### Linux / macOS (recommended)

```bash
chmod +x start.sh
./start.sh
```

Each `./start.sh` run creates one timestamped debug trace at:

`error-logs/run_YYYYMMDD_HHMMSS_RANDOM.txt`

This file includes timestamps plus detailed runtime events (user inputs, model responses, tool calls, tool results, and API request/response tracing).

### Windows (PowerShell or CMD)

```bash
cd ui
npx tsx src/App.tsx
```

> **Note:** The UI starts the Python backend automatically.

---

## Configuration

### Custom Python binary

If your system uses a non-default Python command, set `PYTHON_BIN` before starting.

**Linux / macOS**

```bash
export PYTHON_BIN=python3
```

**Windows (PowerShell)**

```powershell
$env:PYTHON_BIN = "py"
```

### Projects root path

By default, the agent uses this resolution order for project files:

1. `APEK_PROJECTS_ROOT` (or `PROJECTS_ROOT`) if set
2. `/projects`
3. `~/projects` (fallback if `/projects` is not writable)

To force your preferred path (example: `/home/prawesh/projects`):

```bash
export APEK_PROJECTS_ROOT=/home/prawesh/projects
```

Windows PowerShell:

```powershell
$env:APEK_PROJECTS_ROOT = "C:\\Users\\<you>\\projects"
```

---

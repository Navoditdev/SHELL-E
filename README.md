# Shell-E

A terminal-only natural language interface for Linux. Python handles the agent,
Ollama, tools, and shell execution. TypeScript is used only for the OpenTUI UI.

## Run

Requires Linux, Python 3.11+, Bun, and a running Ollama service with a model that
supports tool calling.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bun install
ollama pull qwen3:4b
bun start
```

If Ollama is not already running, start `ollama serve` in another terminal.
Shell-E defaults to the launch directory as its workspace. To select a different
workspace or model:

```bash
SHELL_E_WORKSPACE=/path/to/project SHELL_E_MODEL=qwen3:4b bun start
```

`OLLAMA_HOST` defaults to `http://127.0.0.1:11434`. The TUI uses `.venv/bin/python`
when available, or `python3`; override with `SHELL_E_PYTHON`. See `.env.example`
for configuration names. The Python core reads environment variables; Bun can
load a local `.env` file when launching the TUI.

## First version

- Conversational agent with Ollama streaming text and tool calling.
- Workspace file listing, reading, and filename search.
- Persistent session working directory.
- Exact shell command, explanation, directory, and timeout shown for approval.
- Live stdout/stderr and structured results including exit status.
- Timeouts, output limits, cancellation, and process-group cleanup.
- Conversation and tool history kept in memory during the session.

Enter a task, then type `yes` or `no` when a command needs approval. Rejection
stops the task, including remaining tool calls from that response. `Esc` cancels
the current task, `Ctrl+C` exits, and `PgUp`/`PgDn` scroll the transcript.
`/cd <path>` changes directory within the workspace, `/clear` clears conversation
history, and `/exit` quits.

Commands run through noninteractive Bash with closed stdin. A `cd` inside a
shell command affects that command only; the `change_directory` tool and `/cd`
update the session directory. Interactive programs and sudo are not supported.
Commands have a default 30-second timeout (maximum 120 seconds) and a combined
32 KB output limit. Exceeding the output limit terminates the command. Background
processes are cleaned up when the shell exits. Cancellation terminates the task
and its command process group.

Workspace checks constrain file tools and directory changes. Approved Bash
commands run with your user's permissions and can access paths outside the
workspace; this version is not an OS sandbox.

## Structure

```text
shell-e/
├── exp.py                     # Original Python experiment, unchanged
├── src/
│   ├── shell_e/               # Python core
│   │   ├── config.py          # Workspace, model, host, and limits
│   │   ├── agent.py           # Agent loop and conversation history
│   │   ├── ollama.py          # Streaming Ollama chat adapter
│   │   ├── tools.py           # Tool schemas, validation, and dispatch
│   │   ├── execution.py       # Bash subprocess lifecycle and output
│   │   ├── safety.py          # Workspace path checks
│   │   └── bridge.py          # Local stdin/stdout JSON protocol
│   └── tui/                   # TypeScript OpenTUI interface
│       ├── index.ts           # UI entry point
│       ├── screens/main.ts    # Conversation, approval, and output
│       ├── state/backend.ts   # Python subprocess connection
│       ├── components/        # Space for reusable UI controls
│       └── theme/             # Space for terminal theme definitions
├── tests/                     # Python unittest tests
├── docs/protocol.md           # UI/core message protocol
├── scripts/                   # Development helpers
├── pyproject.toml             # Python package definition
├── requirements.txt           # Python runtime dependencies
└── package.json               # OpenTUI dependencies and Bun scripts
```

The TUI launches the Python core as a child process. JSON lines over stdin/stdout
carry prompts, approvals, cancellation, and agent events. There is no application
HTTP server; only Python's Ollama adapter makes model requests.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
bun run typecheck
```

The Python tests run without third-party dependencies. They cover the core,
process cleanup, the Ollama adapter with a fake HTTP client, and the real Python
bridge subprocess. Live Ollama and terminal rendering require separate smoke
checks after dependency installation.

References: [OpenTUI](https://opentui.com/docs/getting-started/quickstart/) and
[Ollama tool calling](https://docs.ollama.com/capabilities/tool-calling).

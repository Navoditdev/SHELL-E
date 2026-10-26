# Shell-E

Shell-E is a terminal agent for Linux. You describe a task in plain language;
the local Ollama model can inspect files and propose shell commands. Shell-E
shows each command for approval before running it.

The application has two processes:

- A TypeScript terminal UI, rendered by OpenTUI and launched with Bun.
- A Python agent process, which talks to Ollama, validates tool requests, and
  runs approved shell commands.

## Requirements

- Linux, Python 3.11 or newer, and Bash.
- Bun and the project’s installed JavaScript dependencies.
- Ollama running locally (or at a configured URL) with a model that supports
  tool calling.

## Install and run

From the project checkout, create a Python environment, install the Python and
JavaScript dependencies, pull a model, and install Shell-E’s command:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bun install
ollama pull qwen3.5:4b
.venv/bin/python -m pip install -e .
```

Make sure Ollama is running. If it is not already running as a service, start
it in another terminal:

```bash
ollama serve
```

Then start Shell-E:

```bash
.venv/bin/shell-e
```

After activating the environment with `source .venv/bin/activate`, you can run
`shell-e` directly. The editable Python install creates that command and points
it to this checkout. The launcher finds Bun on `PATH`, or falls back to
`.tools/node_modules/.bin/bun` when it exists. It then changes to the checkout
root and runs `src/tui/index.ts`.

Other ways to launch the UI from the checkout are:

```bash
bun start
python3 scripts/start.py
```

`bun start` runs the TUI directly. `scripts/start.py` uses the same launcher as
the installed `shell-e` command. The launcher also supports `shell-e --help`
and `shell-e --version`.

## What happens at startup

1. The launcher starts Bun with the TypeScript UI entry point.
2. The UI starts `python -u -m shell_e.bridge` as a child process. It uses
   `.venv/bin/python` if present, otherwise `python3`; set `SHELL_E_PYTHON` to
   choose a different interpreter.
3. Python loads configuration, creates the agent and Ollama client, then sends
   a `ready` event with the model and current directory.
4. The UI and Python process exchange one JSON object per line over the child
   process’s stdin and stdout. This is a local process connection; Shell-E does
   not run an application web server.
5. When you submit a task, Python sends the conversation to Ollama. The model
   can answer with text or request one of Shell-E’s tools. File tools are
   checked against the workspace. For a shell tool request, the UI displays
   the command, explanation, working directory, and timeout and waits for your
   approval.
6. If approved, Python runs the command with noninteractive Bash and streams
   output back into the UI. The result, including the exit status, is returned
   to the model so it can continue or report back. Rejecting a command stops
   the task and remaining tool calls from that response.

The Python bridge handles the Ollama API requests. The UI only handles
rendering, input, approvals, and the bridge protocol. See
[`docs/protocol.md`](docs/protocol.md) for the message types.

## Configuration

The Python process reads these environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SHELL_E_WORKSPACE` | Current directory when the Python bridge starts | Root directory available to file tools and `/cd` |
| `SHELL_E_MODEL` | `qwen3.5:4b` | Ollama model name |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server URL |
| `SHELL_E_PYTHON` | `.venv/bin/python`, then `python3` | Python executable used by the UI |

The Bun-launched UI loads `.env` values and passes them to Python. Copy
`.env.example` to `.env` in the directory from which Bun starts, then edit the
values as needed. For `shell-e` and `scripts/start.py`, that directory is the
checkout root; for `bun start`, it is the current directory. For a one-off
launch, set variables on the command line:

```bash
SHELL_E_WORKSPACE=/path/to/project \
SHELL_E_MODEL=qwen3.5:4b \
OLLAMA_HOST=http://127.0.0.1:11434 \
.venv/bin/shell-e
```

The `shell-e` and `scripts/start.py` launchers change to the checkout root
before starting Bun, so without `SHELL_E_WORKSPACE` their default workspace is
the checkout. `bun start` keeps the current directory as its default
workspace. Set `SHELL_E_WORKSPACE` to choose the workspace explicitly
regardless of launch method.

Shell-E uses the local model configured above; it does not download models
automatically. Pull the selected model separately with `ollama pull <model>`.

## Using the terminal UI

Enter a task at the prompt. When Shell-E requests shell approval, type `yes` or
`no` and press Enter. Other controls and commands:

| Input | Action |
| --- | --- |
| `Esc` | Cancel the current task or command |
| `Ctrl+C` | Exit Shell-E |
| `PgUp` / `PgDn` | Scroll the transcript |
| `/help` | Show available commands |
| `/cd <path>` | Change the session directory within the workspace |
| `/clear` | Clear the transcript and conversation history |
| `/exit` or `/quit` | Exit Shell-E |

Unknown slash commands are reported and are not sent to the model. A `cd` in a
shell command only affects that command; use `/cd` or the model’s
`change_directory` tool to change the session directory.

## Command execution and limits

Approved commands run in noninteractive Bash with stdin closed. Interactive
programs and `sudo` are not supported. Commands default to a 30-second timeout
and can request at most 120 seconds. Combined stdout and stderr are limited to
32 KB; exceeding the limit terminates the command. Shell background processes
are cleaned up when the command ends. Cancelling a task terminates its command
process group.

File tools and directory changes are restricted to the configured workspace.
Approved Bash commands run with your user’s permissions and can access paths
outside that workspace. Workspace checks are not an operating system sandbox;
review commands before approving them.

The conversation and tool history are kept in memory for the session. `/clear`
resets that history.

## Project layout

```text
src/shell_e/       Python agent, Ollama client, tools, safety checks, and bridge
src/tui/           TypeScript OpenTUI application
scripts/           Setup, launch, checks, and diagnostics
docs/protocol.md   UI-to-Python JSON-lines protocol
tests/             Python and UI helper tests
pyproject.toml     Python package and command entry points
package.json       Bun scripts and OpenTUI dependency
```

## Development

Run the checks from the checkout:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
bun run typecheck
```

`python3 scripts/check.py` runs the Python and UI helper tests. `bun run doctor`
reports missing local runtime dependencies, Ollama availability, and whether
the configured model is installed. `python3 scripts/setup.py` can create the
project virtual environment, install dependencies, capture resolved lock
files, and run the checks and diagnostics.

Live Ollama behavior and terminal rendering need a running Ollama service and a
real terminal; the automated checks do not exercise those.

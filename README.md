# Shell-E

Shell-E is a small terminal agent for Linux. A Python loop sends the current
conversation to a local Ollama model, runs its file tools, and asks before any
shell command. The loop, tools, and command safety checks are the whole app.

## Run

Requirements: Python 3.11+, Ollama, and an installed model with tool calling.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
ollama pull qwen3.5:4b
.venv/bin/python -m pip install -e .
.venv/bin/shell-e
```

Start Ollama separately if it is not already running:

```bash
ollama serve
```

Enter a task at `You>`. The model can inspect workspace files and propose
commands. Shell-E prints each command and its reason, then waits for `y` before
running it. Type `/clear` to reset conversation history or `/quit` to exit.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `SHELL_E_WORKSPACE` | Current directory | Root available to file tools and directory changes |
| `SHELL_E_MODEL` | `qwen3.5:4b` | Ollama model |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server |

For example:

```bash
SHELL_E_WORKSPACE=/path/to/project SHELL_E_MODEL=qwen3.5:4b .venv/bin/shell-e
```

## Agent loop

`src/shell_e/agent.py` owns the learning core: append the user prompt, ask the
model, run returned tools, feed results back, and repeat until the model gives
a final answer or reaches the step limit. `tools.py` defines available tools;
`execution.py` runs approved commands; `safety.py` keeps file access inside the
workspace. `cli.py` is a thin terminal shell around that loop.

Run the core checks with:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

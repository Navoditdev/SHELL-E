import asyncio
from dataclasses import dataclass
import fnmatch
import os
import stat
from pathlib import Path
from typing import Awaitable, Callable

from .config import Config
from .execution import CommandRequest, execute_command
from .safety import workspace_directory, workspace_path


def schema(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": required, "additionalProperties": False}}}


STRING = {"type": "string"}
TOOL_SCHEMAS = [
    schema("list_directory", "List up to 100 workspace directory entries.", {"path": STRING}, ["path"]),
    schema("read_file", "Read a regular workspace text file of at most 16000 bytes.", {"path": STRING}, ["path"]),
    schema("find_files", "Find filenames with * and ? wildcards; bounded search, skipping .git, .venv and node_modules.",
           {"path": STRING, "pattern": STRING}, ["path", "pattern"]),
    schema("change_directory", "Change the session directory within the workspace.", {"path": STRING}, ["path"]),
    schema("execute_command", "Propose a noninteractive Bash command for user approval. cd here does not persist; use change_directory.",
           {"command": STRING, "explanation": STRING,
            "timeoutMs": {"type": "integer", "minimum": 1, "maximum": 120000}}, ["command", "explanation"]),
]


@dataclass
class ToolContext:
    config: Config
    cwd: Path
    approve: Callable[[CommandRequest], Awaitable[bool]]
    on_output: Callable[[str, str], None] = lambda *_: None


def validate(name, args):
    spec = next((t["function"] for t in TOOL_SCHEMAS if t["function"]["name"] == name), None)
    if spec is None:
        raise ValueError(f"Unknown tool: {name}")
    if not isinstance(args, dict):
        raise ValueError("Arguments must be an object")
    for key, value in args.items():
        if key not in spec["parameters"]["properties"]:
            raise ValueError(f"Unknown argument: {key}")
        if key != "timeoutMs" and (not isinstance(value, str) or len(value) > 16000):
            raise ValueError(f"Invalid {key}")
    for key in spec["parameters"]["required"]:
        if not isinstance(args.get(key), str) or not args[key].strip():
            raise ValueError(f"Missing {key}")


async def run_tool(name, args, ctx: ToolContext):
    validate(name, args)
    if name == "execute_command":
        timeout = args.get("timeoutMs", ctx.config.timeout_ms)
        if type(timeout) is not int or not 1 <= timeout <= 120000:
            raise ValueError("Invalid timeoutMs")
        cwd = workspace_directory(ctx.config.workspace, ctx.cwd, ".")
        request = CommandRequest(args["command"], cwd, args["explanation"], timeout)
        if not await ctx.approve(request):
            return {"denied": True, "message": "User rejected the command. Do not retry it or an equivalent command."}
        return await execute_command(request, ctx.config.max_output_bytes, ctx.on_output)
    path = workspace_path(ctx.config.workspace, ctx.cwd, args["path"])
    if name == "change_directory":
        ctx.cwd = workspace_directory(ctx.config.workspace, ctx.cwd, args["path"])
        return {"cwd": str(ctx.cwd)}
    if name == "read_file":
        # Avoid blocking on FIFOs or following a swapped final symlink.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 16000:
                raise ValueError("Expected a regular file of at most 16000 bytes")
            data = handle.read(16001)
        if len(data) > 16000:
            raise ValueError("File exceeds 16000 bytes")
        return {"content": data.decode("utf-8", errors="replace")}
    if name == "list_directory":
        entries = []
        with os.scandir(path) as items:
            for entry in items:
                entries.append({"name": entry.name, "type": "symlink" if entry.is_symlink() else
                                "directory" if entry.is_dir(follow_symlinks=False) else "file"})
                if len(entries) == 100:
                    return {"entries": entries, "capped": True}
        return {"entries": entries, "capped": False}
    pattern = args["pattern"]
    if len(pattern) > 200 or "/" in pattern:
        raise ValueError("Use a filename pattern of at most 200 characters")
    matches, pending, scanned = [], [path], 0
    while pending:
        folder = pending.pop()
        # Revalidate directories before traversing; do not follow symlink entries.
        workspace_directory(ctx.config.workspace, ctx.cwd, str(folder))
        with os.scandir(folder) as items:
            for entry in items:
                scanned += 1
                if scanned > 10000:
                    return {"matches": matches, "capped": True}
                if entry.is_dir(follow_symlinks=False) and entry.name not in {".git", ".venv", "node_modules"}:
                    pending.append(Path(entry.path))
                if entry.is_file(follow_symlinks=False) and fnmatch.fnmatchcase(entry.name, pattern):
                    matches.append(str(Path(entry.path).relative_to(ctx.config.workspace)))
                if len(matches) == 100:
                    return {"matches": matches, "capped": True}
                if scanned % 100 == 0:
                    await asyncio.sleep(0)
    return {"matches": matches, "capped": False}

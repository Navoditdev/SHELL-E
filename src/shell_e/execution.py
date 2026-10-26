"""Noninteractive Bash execution with bounded output and process-group cleanup."""
import asyncio
import codecs
from dataclasses import asdict, dataclass
import os
from pathlib import Path
import signal
from typing import Callable


@dataclass(frozen=True)
class CommandRequest:
    command: str
    cwd: Path
    explanation: str
    timeout_ms: int

    def to_dict(self):
        return {**asdict(self), "cwd": str(self.cwd)}


async def execute_command(request: CommandRequest, max_output_bytes: int = 32_000,
                          on_output: Callable[[str, str], None] = lambda *_: None) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in {"BASH_ENV", "ENV"}}
    process = await asyncio.create_subprocess_exec(
        "/bin/bash", "--noprofile", "--norc", "-c", request.command,
        cwd=request.cwd, env=env, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    result = {"stdout": "", "stderr": "", "exitCode": None,
              "timedOut": False, "cancelled": False, "truncated": False}
    used = 0

    def kill_group(sig):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass

    async def read(stream, name):
        nonlocal used
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while data := await stream.read(4096):
            remaining = max(0, max_output_bytes - used)
            chunk = data[:remaining]
            used += len(chunk)
            text = decoder.decode(chunk)
            result[name] += text
            if text:
                on_output(name, text)
            if len(data) > remaining:
                result["truncated"] = True
                kill_group(signal.SIGKILL)
        tail = decoder.decode(b"", final=True)
        result[name] += tail
        if tail:
            on_output(name, tail)

    readers = [asyncio.create_task(read(process.stdout, "stdout")),
               asyncio.create_task(read(process.stderr, "stderr"))]

    async def finish():
        await process.wait()
        # Shell background jobs must not survive the command.
        kill_group(signal.SIGKILL)
        await asyncio.gather(*readers)

    completion = asyncio.create_task(finish())
    try:
        await asyncio.wait_for(asyncio.shield(completion), request.timeout_ms / 1000)
    except TimeoutError:
        result["timedOut"] = True
        kill_group(signal.SIGKILL)
        await completion
    except asyncio.CancelledError:
        result["cancelled"] = True
        kill_group(signal.SIGKILL)
        await completion
        raise
    finally:
        kill_group(signal.SIGKILL)
        await process.wait()
        await asyncio.gather(*readers, return_exceptions=True)
    result["exitCode"] = process.returncode
    return result

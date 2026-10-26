"""JSON lines over stdin/stdout between the OpenTUI process and Python agent."""
import asyncio
import json
import signal
import sys
import uuid
from contextlib import suppress

from .agent import Agent
from .config import Config
from .ollama import OllamaChat
from .safety import workspace_directory
from .tools import ToolContext


class Bridge:
    def __init__(self, config, emit, chat=None):
        self.config, self.emit = config, emit
        self.task = None
        self.approval = None
        self.approval_id = None
        self.context = ToolContext(config, config.workspace, self.approve,
                                   lambda stream, text: self.emit({"type": "output", "stream": stream, "text": text}))
        self.agent = Agent(chat or OllamaChat(config.host, config.model), self.context, emit)

    def ready(self):
        self.emit({"type": "ready", "model": self.config.model, "cwd": str(self.context.cwd)})

    async def approve(self, request):
        self.approval = asyncio.get_running_loop().create_future()
        self.approval_id = uuid.uuid4().hex
        self.emit({"type": "approval", "id": self.approval_id, **request.to_dict()})
        try:
            return await self.approval
        finally:
            self.approval = None
            self.approval_id = None

    async def run(self, prompt):
        try:
            await self.agent.run(prompt)
        except asyncio.CancelledError:
            self.emit({"type": "status", "text": "Cancelled"})
        except Exception as exc:
            self.emit({"type": "error", "text": str(exc)})
        finally:
            self.emit({"type": "done", "cwd": str(self.context.cwd)})
            self.task = None

    async def handle(self, message):
        kind = message.get("type")
        if kind == "cancel":
            if self.task:
                self.task.cancel()
            return
        if kind == "approval":
            if self.approval and not self.approval.done() and message.get("id") == self.approval_id:
                self.approval.set_result(message.get("approved") is True)
            return
        if self.task:
            raise ValueError("A task is already running")
        if kind == "prompt":
            prompt = message.get("text")
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8000:
                raise ValueError("Expected a prompt of 1–8000 characters")
            self.task = asyncio.create_task(self.run(prompt))
        elif kind == "reset":
            self.agent.reset()
            self.ready()
        elif kind == "cd":
            path = message.get("path")
            if not isinstance(path, str):
                raise ValueError("Expected a directory path")
            self.context.cwd = workspace_directory(self.config.workspace, self.context.cwd, path)
            self.ready()
        else:
            raise ValueError("Unknown bridge message")

    async def close(self):
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None


async def serve():
    def emit(event):
        print(json.dumps(event, ensure_ascii=True), flush=True)

    bridge = Bridge(Config.from_env(), emit)
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=100000)
    protocol = asyncio.StreamReaderProtocol(reader)
    transport, _ = await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)
    main_task = asyncio.current_task()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, main_task.cancel)
    bridge.ready()
    try:
        while line := await reader.readline():
            try:
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ValueError("Expected a JSON object")
                if message.get("type") == "shutdown":
                    break
                await bridge.handle(message)
                # Give new tasks a chance to start before reading the next message.
                await asyncio.sleep(0)
            except (ValueError, TypeError, OSError) as exc:
                emit({"type": "error", "text": str(exc)})
    finally:
        await bridge.close()
        transport.close()


def main():
    try:
        asyncio.run(serve())
    except (KeyboardInterrupt, asyncio.CancelledError, BrokenPipeError):
        pass
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

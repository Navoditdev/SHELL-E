"""Small interactive shell around the Python agent loop."""
import argparse
import asyncio
import sys

from .agent import Agent
from .config import Config
from .execution import CommandRequest
from .ollama import OllamaChat
from .tools import ToolContext


def print_text(text):
    print(text, end="", flush=True)


async def run():
    config = Config.from_env()

    async def approve(request: CommandRequest) -> bool:
        print("\n\nCommand needs approval")
        print(f"Directory: {request.cwd}")
        print(f"Reason: {request.explanation}")
        print(f"$ {request.command}")
        try:
            answer = input("Run it? [y/N] ").strip().lower()
        except EOFError:
            return False
        return answer in {"y", "yes"}

    context = ToolContext(config, config.workspace, approve,
                          lambda _stream, text: print_text(text))
    agent = Agent(OllamaChat(config.host, config.model), context,
                  lambda event: print_text(event.get("text", "")) if event["type"] == "text" else None)
    print(f"Shell-E · {config.model}\nWorkspace: {config.workspace}")
    print("Enter a task, /clear to reset history, or /quit to exit.\n")

    while True:
        try:
            prompt = input("You> ").strip()
            if prompt in {"/quit", "/exit"}:
                return
            if prompt == "/clear":
                agent.reset()
                print("Conversation cleared.\n")
                continue
            if not prompt:
                continue
            print("Agent> ", end="", flush=True)
            await agent.run(prompt)
            print("\n")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return
        except Exception as exc:
            print(f"\nError: {exc}\n", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Shell-E terminal agent.")
    parser.add_argument("--version", action="version", version="shell-e 0.1.0")
    parser.parse_args(argv)
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    except Exception as exc:
        parser.exit(1, f"shell-e: {exc}\n")

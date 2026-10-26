"""Ollama streaming chat adapter. HTTP stays inside the Python core."""
import asyncio
import json
import shlex

from .messages import assistant_message


class OllamaChat:
    def __init__(self, host, model, client_factory=None):
        self.host = host
        self.model = model
        self.client_factory = client_factory

    async def __call__(self, messages, tools, on_text):
        factory = self.client_factory
        network_errors = (OSError,)
        timeout_errors = (TimeoutError,)
        if factory is None:
            try:
                import httpx
            except ImportError as exc:
                raise RuntimeError("Install Python dependencies: .venv/bin/python -m pip install -r requirements.txt") from exc
            factory = httpx.AsyncClient
            network_errors += (httpx.RequestError,)
            timeout_errors += (httpx.TimeoutException,)
        try:
            async with asyncio.timeout(180):
                return await self.stream(factory, messages, tools, on_text)
        except timeout_errors as exc:
            raise RuntimeError("Ollama timed out. Try a smaller task or a smaller model; check that Ollama is responding.") from exc
        except network_errors as exc:
            raise RuntimeError(f"Cannot reach Ollama at {self.host}. Start Ollama with 'ollama serve' and check OLLAMA_HOST. {exc}") from exc

    async def stream(self, factory, messages, tools, on_text):
        message = {"role": "assistant", "content": ""}
        done = False
        size = 0
        async with factory(timeout=120) as client:
            async with client.stream("POST", f"{self.host}/api/chat", json={
                "model": self.model, "messages": messages, "tools": tools, "stream": True,
                "options": {"num_ctx": 16384, "num_predict": 4096},
            }) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode(errors="replace")[:1000]
                    if response.status_code == 404:
                        raise RuntimeError(f"Ollama HTTP 404: model {self.model!r} or endpoint not found. "
                                           f"Check OLLAMA_HOST and run: ollama pull {shlex.quote(self.model)}. {body}")
                    if "support" in body.lower() and "tool" in body.lower():
                        raise RuntimeError("The selected Ollama model does not support tool calling. "
                                           "Set SHELL_E_MODEL to an installed model that supports tool calling, such as qwen3.5:4b.")
                    raise RuntimeError(f"Ollama HTTP {response.status_code}: {body}")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    size += len(line)
                    if size > 100000:
                        raise RuntimeError("Ollama response exceeded the size limit. Try a smaller task.")
                    try:
                        part = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise RuntimeError("Ollama returned invalid JSON in its response stream") from exc
                    if not isinstance(part, dict):
                        raise RuntimeError("Ollama returned an invalid response chunk")
                    if "error" in part:
                        raise RuntimeError(str(part["error"]))
                    delta = part.get("message", {})
                    if not isinstance(delta, dict):
                        raise RuntimeError("Ollama returned an invalid message chunk")
                    text = delta.get("content", "")
                    if not isinstance(text, str):
                        raise RuntimeError("Ollama returned non-text content")
                    if text:
                        message["content"] += text
                        on_text(text)
                    thinking = delta.get("thinking", "")
                    if not isinstance(thinking, str):
                        raise RuntimeError("Ollama returned invalid reasoning content")
                    if thinking:
                        message["thinking"] = message.get("thinking", "") + thinking
                    calls = delta.get("tool_calls", [])
                    if not isinstance(calls, list):
                        raise RuntimeError("Ollama returned invalid tool calls")
                    if calls:
                        message.setdefault("tool_calls", []).extend(calls)
                    if len(message["content"]) + len(message.get("thinking", "")) > 16000:
                        raise RuntimeError("Ollama generated too much text. Try a smaller task.")
                    if len(message.get("tool_calls", [])) > 16:
                        raise RuntimeError("Ollama returned too many tool calls")
                    done = done or part.get("done", False)
        if not done:
            raise RuntimeError("Ollama stream ended before completion")
        return assistant_message(message)

"""Validate model messages before they enter history or reach tool dispatch."""
import json


def assistant_message(raw):
    if not isinstance(raw, dict) or raw.get("role") != "assistant":
        raise ValueError("Invalid Ollama response: expected an assistant message")
    content = raw.get("content", "")
    if not isinstance(content, str):
        raise ValueError("Invalid Ollama response: content must be text")
    calls = raw.get("tool_calls", [])
    if not isinstance(calls, list) or len(calls) > 16:
        raise ValueError("Invalid Ollama response: expected at most 16 tool calls")
    normalized = []
    for call in calls:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict) or not isinstance(function.get("name"), str) or not function["name"]:
            raise ValueError("Invalid Ollama response: tool call has no function name")
        args = function.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid Ollama response: tool arguments are not valid JSON") from exc
        if not isinstance(args, dict):
            raise ValueError("Invalid Ollama response: tool arguments must be an object")
        normalized.append({"function": {"name": function["name"], "arguments": args}})
    message = {"role": "assistant", "content": content}
    if normalized:
        message["tool_calls"] = normalized
    if isinstance(raw.get("thinking"), str):
        message["thinking"] = raw["thinking"]
    return message

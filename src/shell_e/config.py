from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Config:
    workspace: Path
    model: str = "qwen3:4b"
    host: str = "http://127.0.0.1:11434"
    max_steps: int = 8
    timeout_ms: int = 30_000
    max_output_bytes: int = 32_000
    max_history_chars: int = 24_000
    max_tool_result_chars: int = 6_000

    @classmethod
    def from_env(cls):
        workspace = Path(os.getenv("SHELL_E_WORKSPACE", os.getcwd())).resolve(strict=True)
        if not workspace.is_dir():
            raise ValueError("Workspace must be a directory")
        host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        parsed = urlparse(host)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Invalid OLLAMA_HOST")
        return cls(workspace=workspace, model=os.getenv("SHELL_E_MODEL", "qwen3:4b"), host=host)

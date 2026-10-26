"""Command line entry point for the Shell-E terminal UI."""
import os
from pathlib import Path
import shutil
import sys


def main() -> None:
    # In this checkout, shell_e lives at src/shell_e and the TUI is at src/tui.
    root = Path(__file__).resolve().parents[2]
    bun = shutil.which("bun")
    local_bun = root / ".tools/node_modules/.bin/bun"
    if not bun and local_bun.exists():
        bun = str(local_bun)
    if not bun:
        sys.exit("Bun is missing. Install Bun, then run `bun install` in the Shell-E project.")

    os.chdir(root)
    os.execv(bun, [bun, "src/tui/index.ts"])

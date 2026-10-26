"""Command line entry point for the Shell-E terminal UI."""
import argparse
import os
from pathlib import Path
import shutil


def project_root() -> Path:
    """Return the checkout root containing the TUI entry point."""
    return Path(__file__).resolve().parents[2]


def find_bun(root: Path) -> str | None:
    """Find Bun on PATH or in the optional project-local tools directory."""
    bun = shutil.which("bun")
    local_bun = root / ".tools/node_modules/.bin/bun"
    if not bun and local_bun.is_file() and os.access(local_bun, os.X_OK):
        bun = str(local_bun)
    return bun


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Start the Shell-E terminal agent.")
    parser.add_argument("--version", action="version", version="shell-e 0.1.0")
    parser.parse_args(argv)

    root = project_root()
    bun = find_bun(root)
    if not bun:
        parser.exit(1, "Bun is missing. Install Bun and run `bun install` in the Shell-E project.\n")
    entry = root / "src/tui/index.ts"
    if not entry.is_file():
        parser.exit(1, f"Shell-E UI entry point is missing: {entry}\n")
    os.chdir(root)
    try:
        os.execv(bun, [bun, str(entry)])
    except OSError as exc:
        parser.exit(1, f"Could not start Bun ({bun}): {exc}\n")

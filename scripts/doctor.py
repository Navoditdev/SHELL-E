#!/usr/bin/env python3
"""Report all local runtime blockers without modifying the machine."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from shell_e.config import Config


def main():
    failed = False

    def report(ok, label, detail):
        nonlocal failed
        failed |= not ok
        print(f'{"OK" if ok else "MISSING"}: {label}: {detail}')

    report(sys.version_info >= (3, 11), 'Python', sys.version.split()[0])
    httpx = importlib.util.find_spec('httpx') is not None
    report(httpx, 'Python dependencies', 'httpx available' if httpx else 'run python3 scripts/setup.py')
    local = ROOT / '.tools/node_modules/.bin/bun'
    bun = shutil.which('bun') or (str(local) if local.exists() else None)
    report(bool(bun), 'Bun', bun or 'run python3 scripts/setup.py')
    report((ROOT / 'node_modules/@opentui/core/package.json').exists(), 'OpenTUI', 'dependency installation')
    report((ROOT / 'bun.lock').exists(), 'UI dependency lock', 'bun.lock')
    report((ROOT / 'requirements.lock').exists(), 'Python dependency lock', 'requirements.lock')
    config = Config.from_env()
    try:
        with urllib.request.urlopen(f'{config.host}/api/tags', timeout=5) as response:
            models = json.load(response).get('models', [])
        report(True, 'Ollama service', config.host)
        names = {model.get('name') for model in models}
        name = config.model if ':' in config.model else f'{config.model}:latest'
        report(name in names, 'Model', config.model if name in names else f'run ollama pull {config.model}')
    except (OSError, ValueError, urllib.error.URLError) as exc:
        report(False, 'Ollama service', f'{exc}; start ollama serve')
    return int(failed)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        sys.exit(str(exc))

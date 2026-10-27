#!/usr/bin/env python3
"""Install project-local dependencies, capture locks, and check the application."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True, **kwargs)


def main():
    python = ROOT / '.venv/bin/python'
    if not python.exists():
        run([sys.executable, '-m', 'venv', ROOT / '.venv'])
    requirements = 'requirements.lock' if (ROOT / 'requirements.lock').exists() else 'requirements.txt'
    run([python, '-m', 'pip', 'install', '--retries', '0', '--timeout', '15', '-r', requirements])
    # Record the actual resolver output, never invent package versions or hashes.
    resolved = subprocess.check_output([str(python), '-m', 'pip', 'freeze'], cwd=ROOT, text=True)
    (ROOT / 'requirements.lock').write_text(resolved)
    run([python, 'scripts/check.py'])
    run([python, 'scripts/doctor.py'])
    print('Setup complete. Start with: .venv/bin/shell-e')


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, OSError, RuntimeError) as exc:
        print(f'Setup stopped: {exc}', file=sys.stderr)
        raise SystemExit(1)

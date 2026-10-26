#!/usr/bin/env python3
"""Install project-local dependencies, capture locks, and check the application."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=ROOT, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pull-model', action='store_true', help='Download the configured model through the running Ollama service')
    args = parser.parse_args()
    python = ROOT / '.venv/bin/python'
    if not python.exists():
        run([sys.executable, '-m', 'venv', ROOT / '.venv'])
    requirements = 'requirements.lock' if (ROOT / 'requirements.lock').exists() else 'requirements.txt'
    run([python, '-m', 'pip', 'install', '--retries', '0', '--timeout', '15', '-r', requirements])
    # Record the actual resolver output, never invent package versions or hashes.
    resolved = subprocess.check_output([str(python), '-m', 'pip', 'freeze'], cwd=ROOT, text=True)
    (ROOT / 'requirements.lock').write_text(resolved)
    bun = shutil.which('bun')
    local_bun = ROOT / '.tools/node_modules/.bin/bun'
    if not bun and local_bun.exists():
        bun = str(local_bun)
    if not bun:
        npm = shutil.which('npm')
        if not npm:
            raise RuntimeError('Install Bun or npm, then rerun setup.')
        run([npm, 'install', '--prefix', ROOT / '.tools', 'bun', '--fetch-retries=0', '--fetch-timeout=15000'])
        bun = str(local_bun)
    # Bun generates bun.lock on the first successful resolution.
    install = [bun, 'install']
    if (ROOT / 'bun.lock').exists():
        install.append('--frozen-lockfile')
    run(install)
    run([python, 'scripts/check.py'])
    run([bun, 'run', 'typecheck'])
    if args.pull_model:
        run(['ollama', 'pull', os.environ.get('SHELL_E_MODEL', 'qwen3:4b')])
    run([python, 'scripts/doctor.py'])
    print('Setup complete. Start with: python3 scripts/start.py')


if __name__ == '__main__':
    try:
        main()
    except (subprocess.CalledProcessError, OSError, RuntimeError) as exc:
        print(f'Setup stopped: {exc}', file=sys.stderr)
        raise SystemExit(1)

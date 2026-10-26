#!/usr/bin/env python3
"""Run core and UI bridge tests, without requiring a live model or native UI."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
python = root / '.venv/bin/python'
if not python.exists():
    python = Path(sys.executable)
env = {**os.environ, 'PYTHONPATH': str(root / 'src'), 'SHELL_E_PYTHON': str(python)}
commands = [[str(python), '-m', 'unittest', 'discover', '-s', 'tests', '-v']]
node = shutil.which('node')
if node:
    commands += [[node, str(test)] for test in sorted((root / 'tests/tui').glob('*.test.ts'))]
else:
    print('Node is missing; UI helper tests require Node 22.18+.', file=sys.stderr)
    sys.exit(1)
for command in commands:
    result = subprocess.run(command, cwd=root, env=env)
    if result.returncode:
        sys.exit(result.returncode)

#!/usr/bin/env python3
"""Run the Python core tests without requiring a live model."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
python = root / '.venv/bin/python'
if not python.exists():
    python = Path(sys.executable)
env = {**os.environ, 'PYTHONPATH': str(root / 'src')}
result = subprocess.run([str(python), '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=root, env=env)
sys.exit(result.returncode)

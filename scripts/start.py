#!/usr/bin/env python3
"""Launch OpenTUI using the installed or project-local Bun executable."""
import os
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1]
bun = shutil.which('bun')
local = root / '.tools/node_modules/.bin/bun'
if not bun and local.exists():
    bun = str(local)
if not bun:
    sys.exit('Bun is missing. Run: python3 scripts/setup.py')
os.chdir(root)
os.execv(bun, [bun, 'src/tui/index.ts'])

#!/usr/bin/env bash
set -euo pipefail

version="${1:-}"
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "usage: $0 <major.minor.patch>" >&2
  exit 1
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

printf '%s\n' "$version" > VERSION

python3 - "$version" <<'PY'
import json
import re
import sys
from pathlib import Path

version = sys.argv[1]

# pyproject.toml: first top-level version line
p = Path("pyproject.toml")
text = p.read_text()
text, n = re.subn(r'^version = "[^"]+"', f'version = "{version}"', text, count=1, flags=re.M)
if n != 1:
    raise SystemExit("pyproject.toml: could not find a top-level version line")
p.write_text(text)

# package.json: the package "version" key
p = Path("landing-page/package.json")
text = p.read_text()
text, n = re.subn(r'("version": ")[^"]+(")', rf'\g<1>{version}\g<2>', text, count=1)
if n != 1:
    raise SystemExit("landing-page/package.json: could not find version")
p.write_text(text)

# package-lock.json: the lockfile has two top-level version fields
p = Path("landing-page/package-lock.json")
text = p.read_text()
text, n = re.subn(r'("version": ")[^"]+(")', rf'\g<1>{version}\g<2>', text, count=2)
if n != 2:
    raise SystemExit("landing-page/package-lock.json: expected 2 version fields")
p.write_text(text)

# backend/main.py: FastAPI(version=...) and JSON payloads
p = Path("backend/main.py")
text = p.read_text()
text = re.sub(r'version="[^"]+"', f'version="{version}"', text)
text = re.sub(r'"version": "[^"]+"', f'"version": "{version}"', text)
p.write_text(text)

PY

chmod +x "$repo_root/scripts/set_version.sh"
echo "Set version to $version in VERSION, pyproject.toml, backend/main.py, landing-page/package.json, landing-page/package-lock.json"

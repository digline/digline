#!/usr/bin/env bash
# Import every module this tag published, in the interpreter it was installed
# into. The roster comes from `dist_manifest.py`, so a new package is covered
# the moment it is built — which is the whole point: the hardcoded
# `import digline_anthropic, digline_openai, …` line this replaces was the one
# part of the publish workflow that did not pick a new package up on its own,
# and a package missing from it was published and never verified.
#
#   verify_imports.sh <python> <manifest-dir>
set -euo pipefail

python_bin=$1
manifest=$2/imports.txt

[ -s "$manifest" ] || {
  echo "::error title=No modules to import::$manifest is empty, so this would" \
       "verify nothing."
  exit 1
}

"$python_bin" - "$manifest" <<'PY'
import importlib
import pathlib
import sys

modules = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").split()
if not modules:
    raise SystemExit("no modules listed: this cannot pass by importing nothing")
for module in modules:
    importlib.import_module(module)
print(f"imported {len(modules)}: {', '.join(modules)}")
PY

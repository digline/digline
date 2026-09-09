#!/usr/bin/env bash
# The front page's quickstart, run inside the image.
#
#     docker/smoke.sh [image]        # default: digline:smoke
#
# The one test that exercises what the image actually *is* — the entrypoint,
# the working directory, the uid, and a repository arriving as a bind mount.
# Nothing here reads the source tree except `README.md`, on purpose: the image
# installs digline from PyPI, so what it runs has to be what a reader would
# run, from the page a reader would copy it off.
#
# It lives in a file rather than inside a workflow because two workflows run
# it: `ci.yml` builds the image without pushing and calls this, and
# `docker-publish.yml` calls it before the push. A second copy of a seventy-line
# smoke test would drift, and the copy that drifts is always the one guarding
# the release.
#
# Run it from the repository root. It needs `docker`, `python3` and a `README.md`
# beside it.
set -euo pipefail

IMAGE="${1:-digline:smoke}"
work="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/digline-smoke"
rm -rf "$work" && mkdir -p "$work"

# Extracted from README.md rather than copied into this file: a second copy of
# the suite would drift, and `tests/test_readme.py` already holds the front page
# to exactly one runnable block.
WORK="$work" python3 - <<'PY'
import os, pathlib, re
text = pathlib.Path("README.md").read_text(encoding="utf-8")
blocks = re.findall(r"```python\n(.*?)```", text, re.DOTALL)
assert len(blocks) == 1, f"expected one suite on the front page, found {len(blocks)}"
pathlib.Path(os.environ["WORK"], "suite.py").write_text(blocks[0], encoding="utf-8")
PY

# `--user`, because the checkout is not owned by the image's uid 1000 — the
# case README.md documents, run here rather than only described.
digline() {
  docker run --rm --user "$(id -u):$(id -g)" -v "$work:/work" "$IMAGE" "$@"
}

digline --help > /dev/null
digline run --suite suite.py
digline promote --suite suite.py --run latest

# "Now make it worse": the sign-off leaves the second answer, which is the
# regression the front page shows.
WORK="$work" python3 - <<'PY'
import os, pathlib
suite = pathlib.Path(os.environ["WORK"], "suite.py")
source = suite.read_text(encoding="utf-8")
sign_off = " — Northwind Support"
assert source.count(sign_off) == 2, source.count(sign_off)
head, _, tail = source.rpartition(sign_off)
suite.write_text(head + tail, encoding="utf-8")
PY

digline run --suite suite.py
set +e
digline compare --suite suite.py --run latest
status=$?
set -e
if [ "$status" -ne 1 ]; then
  echo "compare should have exited 1 on a worse run, exited $status"; exit 1
fi

# Decision 2 of CLAUDE.md, checked on the filesystem: everything the run wrote
# is in the mounted repository, and it belongs to the user who owns that
# repository rather than to root.
test -f "$work/.digline/northwind/baselines/support.json"
test -d "$work/.digline/northwind/runs/support"
test -f "$work/.digline/.gitignore"
if find "$work/.digline" ! -user "$(id -u)" -print -quit | grep -q .; then
  echo "the run left files the caller does not own:"
  find "$work/.digline" ! -user "$(id -u)" -ls
  exit 1
fi
echo "quickstart ok: exit 0 before the break, exit 1 after it"

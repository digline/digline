"""Copy into `to-publish/` only the distributions the index does not have.

The workspace builds every package on every tag. Most tags move one of them, so
most of what is built is already released — and asking an index to accept a file
it already has is asking it to do the one thing it must never do. Skipping is
cheaper and says out loud, in the log, what is going out and what is not.

Reads `INDEX`; writes `count` to `GITHUB_OUTPUT` so the publish step can be
skipped rather than fail on an empty directory.

`OUT` moves the copies elsewhere, for a selection that is read and not
published: the `testpypi` job asks PyPI what it would take, before the `pypi`
job waits for its reviewer. With `SUMMARY_TITLE` set, the selection is also
written to the job summary under that title, which is where the reviewer
reads it. (gate_summary.py says why it is there and not in a session's report.)
"""

import os
import pathlib
import shutil
import urllib.error
import urllib.request

INDEX = os.environ["INDEX"].rstrip("/")
DIST = pathlib.Path("dist")
OUT = pathlib.Path(os.environ.get("OUT", "to-publish"))
SUMMARY_TITLE = os.environ.get("SUMMARY_TITLE", "")


def name_and_version(path: pathlib.Path) -> tuple[str, str]:
    if path.name.endswith(".whl"):
        name, version = path.name.split("-")[:2]
    else:
        name, version = path.name.removesuffix(".tar.gz").rsplit("-", 1)
    return name.replace("_", "-").lower(), version


def already_released(name: str, version: str) -> bool:
    url = f"{INDEX}/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=30):
            return True
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False
        raise


OUT.mkdir(parents=True, exist_ok=True)
seen: dict[tuple[str, str], bool] = {}
rows: list[tuple[str, str, str]] = []
for dist in sorted(DIST.iterdir()):
    if dist.suffix not in {".whl", ".gz"}:
        continue
    key = name_and_version(dist)
    if key not in seen:
        seen[key] = already_released(*key)
    if seen[key]:
        print(f"skip     {dist.name}  — {key[0]} {key[1]} is already on the index")
        rows.append(("skip", dist.name, "already on the index"))
    else:
        print(f"publish  {dist.name}")
        rows.append(("publish", dist.name, ""))
        shutil.copy2(dist, OUT / dist.name)

count = len(list(OUT.iterdir()))
print(f"\n{count} file(s) to publish to {INDEX}")
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
    handle.write(f"count={count}\n")

summary = os.environ.get("GITHUB_STEP_SUMMARY")
if SUMMARY_TITLE and summary:
    published = [row for row in rows if row[0] == "publish"]
    lines = [
        f"### {SUMMARY_TITLE}",
        "",
        f"**{len(published)} publish, {len(rows) - len(published)} skip**, "
        f"against {INDEX}",
        "",
        *(f"- publish `{name}`" for _, name, _ in published),
    ]
    with open(summary, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n\n")

"""Write the counts a reviewer reads at the PyPI gate into the job summary.

The `pypi` environment waits for a person, and GitHub notifies that person the
moment it starts waiting. A session that watches the run and reports the counts
is racing the click: on digline-anthropic-v0.6.1 the wait lasted ten seconds,
the session polled every twenty, and the counts arrived after the approval. So
the counts go where the click is. GitHub shows job summaries on the run's page,
which is where *Review deployments* is, and they are written before the `pypi`
job starts waiting. (RELEASING.md, *Status*, digline-anthropic-v0.6.1)

  gate_summary.py twine <twine-output>
  gate_summary.py install <label> <imports-output> <run-stderr>

Each reads a file a step already wrote, and appends one section to
`$GITHUB_STEP_SUMMARY`. A count it cannot find is written as *not found*,
never as zero: a summary that read `0 PASSED` because the line moved would be
a green nobody checked.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

NOT_FOUND = "*not found in the step's output*"


def twine_section(output: str) -> str:
    """How many files `twine check --strict` passed, and which."""
    passed = re.findall(r"^Checking (\S+): .*PASSED", output, re.MULTILINE)
    lines = ["### `twine check --strict`", ""]
    if not passed:
        lines.append(f"PASSED: {NOT_FOUND}")
    else:
        lines.append(f"**{len(passed)} PASSED**")
        lines.append("")
        lines.extend(f"- `{name}`" for name in passed)
    return "\n".join(lines) + "\n"


def install_section(label: str, imports: str, run_stderr: str) -> str:
    """What installed from an index: the modules imported, and the quickstart's
    calls, in the words the two steps printed."""
    imported = re.search(r"^imported (\d+): (.+)$", imports, re.MULTILINE)
    calls = [
        line.strip()
        for line in run_stderr.splitlines()
        if line.startswith("digline:") and "call" in line
    ]
    lines = [f"### Installed from {label}", ""]
    if imported:
        lines.append(f"- **imported {imported.group(1)}**: {imported.group(2)}")
    else:
        lines.append(f"- imported: {NOT_FOUND}")
    if calls:
        lines.extend(f"- quickstart: `{line}`" for line in calls)
    else:
        lines.append(f"- quickstart's calls: {NOT_FOUND}")
    return "\n".join(lines) + "\n"


def append(section: str) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        # Outside Actions, say what would have been written.
        print(section)
        return
    with open(summary, "a", encoding="utf-8") as handle:
        handle.write(section + "\n")


def main(argv: list[str]) -> int:
    match argv:
        case ["twine", path]:
            append(twine_section(pathlib.Path(path).read_text(encoding="utf-8")))
        case ["install", label, imports, run_stderr]:
            append(
                install_section(
                    label,
                    pathlib.Path(imports).read_text(encoding="utf-8"),
                    pathlib.Path(run_stderr).read_text(encoding="utf-8"),
                )
            )
        case _:
            print(__doc__, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

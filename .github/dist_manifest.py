"""Who is in `dist/`, in the three shapes the verification steps need.

The publish workflow proves a released wheel installs from the index and
imports. Two halves of that check used to be **hardcoded lists** — a
`pip install digline digline-anthropic …` line and an
`import digline_anthropic, digline_openai, …` line beside it — and
`RELEASING.md` had a whole section warning that a new package missing from
them is "published and never verified: the failure that looks like success".

A list that has to be edited by hand is the one thing in this workflow that
does not pick a new package up on its own. Everything else — discovery,
`uv build --all-packages`, `select_unpublished.py`, both upload steps — is
glob-driven. So is this now: the wheels in `dist/` are the roster, and the
roster is what the job was built from a moment earlier.

Writes three files into the directory named by `argv[1]`:

    pins.txt      digline==0.7.2        exact, for the real index
    names.txt     digline               unversioned, for TestPyPI
    imports.txt   digline_mcp           module names, '-' becomes '_'

`pins.txt` holds the versions this tag actually built, which is what stops a
lagging index quietly resolving the *previous* release and passing anyway.
`names.txt` is unversioned on purpose: TestPyPI resolves against a different
set of uploads, and pinning there would fail for a reason that says nothing
about this release.

**`--excluding name==version …` leaves packages out of all three files, and
says which and why** (#717). It is the `pypi` job's install check that passes
it, with what `plugins_against_core.py` classified in `testpypi` as excluded by
its own cap: a plugin PyPI already serves whose range on digline stops below
this core. Installed beside this core it cannot resolve on any index, and
before this option every minor that raised the plugins' caps turned the check
red ten times out of ten. Leaving it out is a reading, not a skip, so each one
is named in the log with the reason, and three exclusions are refused rather
than applied:

- the core, which this check exists to install;
- a name `dist/` does not hold, which says the two readings disagree;
- a name without a version: an exclusion is of the served version that was
  classified.

**A version this tag publishes is never left out.** The classification reads
the newest version PyPI served before the upload. When `dist/` holds a newer
one, this tag publishes it and nothing has verified it yet, so it stays in the
manifest and the log says so.
"""

import pathlib
import sys


def name_and_version(wheel: pathlib.Path) -> tuple[str, str]:
    """`digline_mcp-0.1.1-py3-none-any.whl` -> `("digline-mcp", "0.1.1")`.

    The same parse as `select_unpublished.py`: a wheel filename is
    `name-version-…`, and the distribution name is normalised back from the
    underscores the build wrote into it.
    """
    name, version = wheel.name.split("-")[:2]
    return name.replace("_", "-").lower(), version


def _refuse(sentence: str) -> int:
    print(
        f"::error title=An exclusion that cannot be right::{sentence}", file=sys.stderr
    )
    return 1


def main(argv: list[str]) -> int:
    out = pathlib.Path(argv[1] if len(argv) > 1 else "manifest")
    excluding = argv[3:] if len(argv) > 2 and argv[2] == "--excluding" else []

    found = dict(
        sorted(name_and_version(w) for w in pathlib.Path("dist").glob("*.whl"))
    )
    if not found:
        # A check that can pass by finding nothing is the vacuously green
        # assertion `CLAUDE.md` decision 3 refuses. Empty here means `dist/` is
        # not what the job thinks it is, which is worth failing loudly for.
        print(
            "::error title=No wheels to verify::dist/*.whl matched nothing, so "
            "there is no package to hold the index to. This cannot pass by "
            "finding nothing.",
            file=sys.stderr,
        )
        return 1

    for exclusion in excluding:
        name, _, version = exclusion.partition("==")
        if not version:
            return _refuse(
                f"{exclusion} is not name==version: an exclusion is of the served "
                "version plugins_against_core.py classified"
            )
        if name == "digline":
            return _refuse(
                f"{exclusion} names the core, which this check exists to install"
            )
        if name not in found:
            return _refuse(
                f"{exclusion} is not in dist/, so the classification and the "
                "roster this tag built disagree"
            )
        if found[name] != version:
            print(
                f"kept {name} {found[name]}: the classification excluded the "
                f"served {version}, and this tag publishes {found[name]}, which "
                "nothing has verified yet"
            )
            continue
        del found[name]
        print(
            f"left out {name} {version}: excluded by its own cap, which stops "
            "below this core, as plugins_against_core.py classified it in the "
            "testpypi job. This release owes it a release"
        )
        print(
            f"::notice title=Left out of the install check::{name} {version} is "
            "excluded by its own cap (plugins_against_core.py)"
        )

    out.mkdir(parents=True, exist_ok=True)
    (out / "pins.txt").write_text(
        "".join(f"{n}=={v}\n" for n, v in found.items()), encoding="utf-8"
    )
    (out / "names.txt").write_text("".join(f"{n}\n" for n in found), encoding="utf-8")
    (out / "imports.txt").write_text(
        "".join(f"{n.replace('-', '_')}\n" for n in found), encoding="utf-8"
    )
    print(f"{len(found)} package(s) in dist/: {', '.join(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

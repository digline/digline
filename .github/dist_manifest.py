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


def main(argv: list[str]) -> int:
    out = pathlib.Path(argv[1] if len(argv) > 1 else "manifest")
    out.mkdir(parents=True, exist_ok=True)

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

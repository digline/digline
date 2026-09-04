"""A page in `docs/` and the line it needs in another repository.

The sibling of `tests/test_adr.py`, which does this for the decision records,
and of `test_examples.py`, which does it for the example READMEs. Between them
they covered everything `sync-docs.sh` copies **except the top-level pages of
`docs/` itself** — `guide.md`, `api.md`, `view.md` and the rest.

That gap went unnoticed because no page had been added since those two gates
were written. `docs/diff.md` is the first, and finding the gap by adding the
page is the good outcome: the alternative is finding it in the `docs` job of
`publish.yml`, which runs *after* PyPI, with the version already spent.
"""

from __future__ import annotations

from pathlib import Path

from tests._site import nav_lists, require_site_config

ROOT = Path(__file__).resolve().parents[1]


def doc_pages() -> list[str]:
    """The pages of `docs/`, by the name their page will have.

    Non-recursive on purpose: `sync-docs.sh` copies the whole tree with
    `cp -R docs/. product/`, so `docs/<name>.md` becomes `product/<name>.md`,
    and `docs/adr/<name>.md` becomes `product/adr/<name>.md` — which is
    `test_adr.py`'s subject and not this one's. One gate per directory, so a
    failure names one rule.

    `CHANGELOG.md` and `ROADMAP.md` are also pages but live at the repository
    root, where a reader arriving on GitHub looks for them. They are not in
    `docs/` and are not this gate's business either.
    """
    return sorted(path.stem for path in (ROOT / "docs").glob("*.md"))


def test_the_docs_glob_still_finds_the_pages() -> None:
    """A guard on the guard: an empty list would make the check below pass over
    nothing and prove nothing."""
    found = doc_pages()
    assert len(found) >= 6, found
    # The decisions have their own gate, and a name appearing in both would mean
    # one of the two globs had started reaching into the other's directory.
    assert not any(name[0].isdigit() for name in found), found
    assert "guide" in found and "api" in found


def test_every_docs_page_is_in_the_site_nav() -> None:
    """A page added here needs one line in another repository.

    `sync-docs.sh` copies `docs/<name>.md` to `docs/product/<name>.md`, and
    mkdocs builds `--strict`: a page in the docs tree and not in `nav` is a
    warning, and a warning is a failed build. That build is the last job of
    `publish.yml` and runs *after* PyPI, so the first time anyone sees the
    mistake the version is already spent.

    The `docs` job in `ci.yml` catches it too, by running the real build. This
    exists beside it because it names the page and the line to add, in a second,
    instead of leaving a reader to read mkdocs' warning about a path they did
    not write.
    """
    config = require_site_config()
    nav = config.read_text(encoding="utf-8")
    missing = [name for name in doc_pages() if not nav_lists(nav, f"product/{name}.md")]
    assert not missing, (
        f"docs/{missing[0]}.md becomes the page product/{missing[0]}.md, which "
        f"{config} does not list in its nav — so `mkdocs build --strict` fails "
        f"and the site is not rebuilt. Add it under `- Docs:`, in the "
        f"`- Reference:` sub-list if it documents one command:\n"
        f'          - "digline {missing[0]}": product/{missing[0]}.md\n'
        f"Missing: {', '.join(missing)}. "
        "If that path is a checkout of your own, it may simply be behind "
        "origin — the entry is added in digline/digline.dev, not here."
    )

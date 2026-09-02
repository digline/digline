# Contributing

Thanks for looking. A few things worth knowing before you open a pull request.

- **Run the gates**: `uv sync --all-packages`, then `pytest -m "not live"`,
  `ruff format --check .`, `ruff check .`, `pyright`. All four are green on
  `main` and CI runs them on 3.12 and 3.13.
- **`tests/test_layering.py` is not a style test.** It keeps `digline.core`
  pure and importable on its own. If it fails, the change is wrong, not the test.
- **Every assertion needs a failing case.** A check that cannot fail is a bug
  (fixed decision 3), and the test that proves it can is the one that says so.
- **Decisions in `CLAUDE.md` marked fixed need an ADR in `docs/adr/` first**,
  not a pull request that quietly works around them.
- **`-m live` costs money** and needs `ANTHROPIC_API_KEY` *and* `DIGLINE_LIVE=1`.
  Never required to contribute.
- **A fifth gate runs only in CI.** The `docs` job builds the digline.dev site
  `--strict` on every push, from your branch's docs. An example or an ADR added
  here needs a nav line in *that* repository, and without it the build fails —
  `RELEASING.md` names the line to add. Nothing you run locally catches this
  unless you have the site checked out beside this repository.

Small commits, imperative English messages. Open an issue first if the change
touches a boundary — it is cheaper to disagree before the code.

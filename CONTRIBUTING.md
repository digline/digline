# Contributing

Thanks for looking. A few things worth knowing before you open a pull request.

- **Run the gates**: `uv sync --all-packages --locked`, then
  `pytest -m "not live"`, `ruff format --check .`, `ruff check .`, `pyright`.
  All of them are green on `main`, and CI runs them on 3.12 and 3.13 — the
  `gates` job of `.github/workflows/ci.yml` is the list, and this is a copy of
  it. `--locked` matches CI: it refuses a `uv.lock` that has fallen behind
  `pyproject.toml` rather than rewriting it, so a lock you forgot to commit
  fails here instead of passing locally and reddening the pull request.
- **`tests/test_layering.py` is not a style test.** It keeps `digline.core`
  pure and importable on its own. If it fails, the change is wrong, not the test.
- **Every assertion needs a failing case.** A check that cannot fail is a bug
  (fixed decision 3), and the test that proves it can is the one that says so.
- **If you add a flag that turns something on, the flag's tests do not cover
  the default.** They feel like they do, which is why this is written down.
  Measured on `digline view --allow-promote` (ADR 0032): the refusal was deleted
  from `do_POST`, and **48 tests exercising the flag all passed** — every
  promotion through the enabled server, every refusal it forwards, the `Host`
  and `Origin` guards. Not one of them can see a default that stopped refusing,
  because not one of them runs on the default. Five tests caught it, and all
  five were written about the *off* state.

  So the rule, for the next opt-out as much as that one: **mutate the default
  away and run the suite.** If it stays green, what you have tested is the
  feature, not the boundary — and a boundary is the only reason an opt-out
  exists. The same run is what catches a test that *looks* like it covers the
  off state and cannot: one here went green under the mutation because its
  fixture had a single run that was already the baseline, so no row could have
  carried the button on any server at all.
- **If you add a guard in front of another one, the old guard's tests go
  empty.** A request that the new guard refuses never reaches the old one, and
  a test expecting a refusal cannot tell whose it got. When `digline view
  --allow-promote` gained its launch key (ADR 0033), the tests of the `Origin`
  check, the rebinding guards and the walk over every refusal type would all
  have passed **with their guards deleted**. The key refused first, and a
  403 from the key reads the same as a 403 from the origin check.

  So, for every test of a guard that now sits behind yours: **send what your
  guard asks for**, so the request reaches the guard the test names. Assert
  the sentence as well as the status, so the refusal says whose it is. Then
  **mutate the old guard away and run the suite.** Green means the test was
  already testing yours. This is the same family as the flag bullet above,
  where a test stays correct about a request while what stands in front of
  it moves, and it has four instances in one week.
- **Decisions in `CLAUDE.md` marked fixed need an ADR in `docs/adr/` first**,
  not a pull request that quietly works around them.
- **`-m live` costs money** and needs `ANTHROPIC_API_KEY` *and* `DIGLINE_LIVE=1`.
  Never required to contribute.
- **One gate runs only in CI, and it is required.** The `docs` job builds the
  digline.dev site `--strict` from your branch's docs, and `main` will not take
  a pull request that breaks it. A link that resolves on GitHub and not on the
  site fails here and nowhere else. An example or an ADR added here also needs
  a nav line in *that* repository — but that one does not fail your pull
  request: it is admitted as `info` precisely because the entry lands after the
  record does. `RELEASING.md` names the line to add. Nothing you run locally
  catches any of this unless you have the site checked out beside this
  repository.

Small commits, imperative English messages. Open an issue first if the change
touches a boundary — it is cheaper to disagree before the code.

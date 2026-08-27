# Changelog

What changed for you, three lines a version. The reasoning lives in
[`docs/adr/`](docs/adr/); this says what to expect.

## 0.1.2 — 2026-08-27

- **Fixed:** a rubric score landing exactly on the threshold inside `Repeated`
  produced `error` instead of `pass`.
- **Changed:** every assertion that asks a judge now sends one prompt shape —
  instruction first, `Output to judge:` last and once, exported as
  `JUDGE_OUTPUT_LABEL`. `Faithfulness` used a different label and a trailing
  line; judges that parsed the old shape need updating.
- **Added:** `HttpTarget`, for an application digline cannot import.

## 0.1.1 — 2026-08-27

- **Changed:** `digline --help` describes the command instead of printing the
  module's docstring.

## 0.1.0 — 2026-08-26

- First release: the offline cycle — write a suite, run, promote, compare,
  report — with the baseline committed in your own repository.

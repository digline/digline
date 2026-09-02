# The runs ADR 0006 was written about

Two real runs of `brief-judge`, copied verbatim out of
[digline/brief](https://github.com/digline/brief)'s own `fixtures/`, plus the
human marks the suite judged against. Verbatim and not reduced on purpose: the
`config_hash` matches on both sides, the artifact digests are the real ones, and
a test that asserted against a hand-trimmed copy would be asserting against
something nobody ran.

| file | what it is |
| --- | --- |
| `2026-09-01T12-44-02-518586-…json` | the promoted baseline |
| `2026-09-01T12-29-17-700450-…json` | fifteen minutes earlier, the run that cried wolf |
| `labels.json` | case id → the mark, extracted from `brief`'s `cases/brief.json` |

Both were produced from the same suite, the same prompt files and the same
`config_hash` (`98fc65b1e49e930e`). **Nothing changed between them.** One case —
`2026-08-24-evals-skills-for-coding-agents` — went 5/5, then 2/5, then 5/5
again, and the run-level accuracy moved by one case in twenty-one and came back:

| | `agrees_with_mark` on that case | precision | accuracy |
| --- | --- | --- | --- |
| `12-29-17` | **0.4** — samples `[1, 1, 0, 0, 0]` | 0.642857 | 0.714286 |
| `12-44-02` | **1.0** — samples `[1, 1, 1, 1, 1]` | 0.666667 | 0.761905 |

Before ADR 0006 the earlier run made `compare` exit 1 with two findings: the
per-case flip, and `accuracy` falling from 0.761905 to 0.714286. A developer
went looking for the regression and there was nothing there.

`labels.json` is here because a run file does not carry the marks — it records
what was judged, not what the case was — and §7 needs them to evaluate the
aggregate once per sample index. Only the marks are copied: no case text, no
`vars`, no metadata.

The three-run story in the ADR keeps only its last two runs here. The first 5/5
run is not in the fixtures; `12-44-02` reproduces its numbers to six decimal
places and stands in for it as the baseline, which is what `brief` promoted.

`tests/test_noise_floor.py` reads these. A change that makes `12-29-17` read
"got worse" at the aggregate again is a change that undoes ADR 0006.

## Where these came from

Copied on 2026-09-02 from a clean checkout of
[digline/brief](https://github.com/digline/brief) at `2ff19d6`.

| what | brief path | last changed there |
| --- | --- | --- |
| both run files | `fixtures/` | `ba6cef7`, 2026-09-01 |
| the marks behind `labels.json` | `cases/brief.json` | `9cbf904`, 2026-08-27 |
| `prompts/item.txt`, `prompts/judge.txt` | recorded *inside* the run files, as `artifacts` | `9cbf904`, 2026-08-27 |

The two prompts are the third row because a run records the files that were
under test, contents and all — so copying the runs copied `brief`'s judge prompt
along with them. It is `brief`'s own file, already published in the same
organisation, and the digests in the documents (`3ce6ed3b9b59`,
`05c20df6d49b`) are the ones that repository's working tree still produces. It
is named here rather than left to be discovered, because a prompt is where an
end company's rules end up and ADR 0003 is about not moving one by accident.

**These files are read-only.** `test_the_fixtures_are_the_bytes_that_were_copied`
pins the SHA-256 of each, so a fixture edited in place to make a test pass fails
the build instead — which is the failure that would otherwise turn "asserted
against the real run" into "asserted against a run we adjusted until it agreed".
Re-copying from `brief` means updating the digests here in the same commit, and
saying why.

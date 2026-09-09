# digline operator: draw

**One check dipped and did not repeat. Treated as noise.** No escalation. AGENTS.md §3: a dip that does not recur on re-run is sampling noise — documented here, and that is the whole of it.

Suite `suite.py`, cadence `0 6 * * 1`, escalating: no.

The operator watches the measurement; it does not repair the system. Fixing this belongs to whoever owns the prompt — this document is the handover.

## 1. The fact

Machine truth, from `digline compare --json full`. Reproducible, and not prose.

| run | seed | exit | worse | unjudged | within noise |
| --- | ---: | ---: | :---: | -------: | -----------: |
| `2026-09-09T12-30-37-298678-00-00-4d2ac7a7f606b8de` | 0 | 1 | yes | 0 | 0 |
| `2026-09-09T12-30-37-505283-00-00-4d2ac7a7f606b8de` | 1 | 0 | no | 0 | 0 |

Suite `suite.py`, output version 1. The configuration of the system under test did not change; the judge's configuration did not change; the suite itself did not change.

## 2. The dossier

Ran the suite once and re-ran it 1 time(s). The stopping rule was `max_reruns = 2`, declared in `operator.toml` before anything ran.

Spend: 6 calls to the target across 2 run(s), against a declared cycle budget of 12. Each run: 3 cases × 1 sample = 3 calls to the target; each answer is judged 3 times by llm_rubric.

**Run `2026-09-09T12-30-37-298678-00-00-4d2ac7a7f606b8de` (seed 0, exit 1)**

| case | check | outcome | before | after | measured floor |
| ---- | ----- | ------- | -----: | ----: | -------------- |
| `is-it-waterproof` | `llm_rubric` | regressed | 0.9104 | 0.5279 | no interval (a flip is a regression whatever the noise said) |

**Run `2026-09-09T12-30-37-505283-00-00-4d2ac7a7f606b8de` (seed 1, exit 0)**

| case | check | outcome | before | after | measured floor |
| ---- | ----- | ------- | -----: | ----: | -------------- |
| `how-do-i-return` | `llm_rubric` | unchanged | 0.8947 | 0.8961 | 0.8603–0.9221 across 3 samples |
| `is-it-waterproof` | `llm_rubric` | unchanged | 0.9104 | 0.9055 | 0.8694–0.9369 across 3 samples |
| `where-is-my-order` | `llm_rubric` | unchanged | 0.8913 | 0.9005 | 0.8700–0.9309 across 3 samples |

No regression was present in every run of this cycle.

## 3. The judgment

**This layer was not run.** It is the only part of this document that a model writes, and it is an explicit opt-in: the key was not configured for this cycle. Layers 1 and 2 above are complete and were produced without one.

What stands in its place is the deterministic classification, **draw**, and the rule it came from — both stated at the top of this document. Neither is an opinion; that is the difference.

---

No baseline was promoted, and none can be: `promote` is absent from the operator's surface by construction. A baseline is an approved reference, and the approval is a person's.

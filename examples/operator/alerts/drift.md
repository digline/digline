# digline operator: drift

**A drop repeated past the declared stopping rule.** Escalated. AGENTS.md §3: a dip that recurs is drift, and drift is investigated — the model, the judge, the prompt, the dependency floor, in that order of likelihood.

Suite `suite.py`, cadence `0 6 * * 1`, escalating: yes.

The operator watches the measurement; it does not repair the system. Fixing this belongs to whoever owns the prompt — this document is the handover.

## 1. The fact

Machine truth, from `digline explain --json`: the fact list digline renders its own reading from. Reproducible, and not prose.

| run | seed | exit | unjudged | within noise |
| --- | ---: | ---: | -------: | -----------: |
| `2026-09-11T06-15-42-145385-00-00-4d2ac7a7f606b8de` | 0 | 1 | 0 | 0 |
| `2026-09-11T06-15-42-337456-00-00-4d2ac7a7f606b8de` | 1 | 1 | 0 | 0 |
| `2026-09-11T06-15-42-527716-00-00-4d2ac7a7f606b8de` | 2 | 1 | 0 | 0 |

Exit `0`: nothing got worse. `1`: something did. `2`: the run could not be judged. That is digline's contract, AGENTS.md §6.

Suite `suite.py`, output version 1. The suite itself did not change. Underneath it, nothing differed: not the system under test, not the judge, not a file under test.

## 2. The dossier

Ran the suite once and re-ran it 2 time(s). The stopping rule was `max_reruns = 2`, declared in `operator.toml` before anything ran.

Spend: 9 calls to the target across 3 run(s), against a declared cycle budget of 12. Each run: 3 cases × 1 sample = 3 calls to the target; each answer is judged 3 times by llm_rubric.

**Run `2026-09-11T06-15-42-145385-00-00-4d2ac7a7f606b8de` (seed 0, exit 1)**

| case | check | outcome | before | after | measured floor |
| ---- | ----- | ------- | -----: | ----: | -------------- |
| `is-it-waterproof` | `llm_rubric` | regressed | 0.9104 | 0.5279 | no interval (a flip is a regression whatever the noise said) |

**Run `2026-09-11T06-15-42-337456-00-00-4d2ac7a7f606b8de` (seed 1, exit 1)**

| case | check | outcome | before | after | measured floor |
| ---- | ----- | ------- | -----: | ----: | -------------- |
| `is-it-waterproof` | `llm_rubric` | regressed | 0.9104 | 0.5750 | no interval (a flip is a regression whatever the noise said) |
| `how-do-i-return` | `llm_rubric` | unchanged | 0.8947 | 0.8961 | 0.8603–0.9221 across 3 samples |
| `where-is-my-order` | `llm_rubric` | unchanged | 0.8913 | 0.9005 | 0.8700–0.9309 across 3 samples |

**Run `2026-09-11T06-15-42-527716-00-00-4d2ac7a7f606b8de` (seed 2, exit 1)**

| case | check | outcome | before | after | measured floor |
| ---- | ----- | ------- | -----: | ----: | -------------- |
| `is-it-waterproof` | `llm_rubric` | regressed | 0.9104 | 0.5298 | no interval (a flip is a regression whatever the noise said) |
| `how-do-i-return` | `llm_rubric` | unchanged | 0.8947 | 0.8973 | 0.8603–0.9221 across 3 samples |
| `where-is-my-order` | `llm_rubric` | unchanged | 0.8913 | 0.8814 | 0.8700–0.9309 across 3 samples |

Present in every run of this cycle: `is-it-waterproof` / `llm_rubric`.

## 3. The judgment

**This layer was not run.** It is the only part of this document that a model writes, and it is an explicit opt-in: the key was not configured for this cycle. Layers 1 and 2 above are complete and were produced without one.

What stands in its place is the deterministic classification, **drift**, and the rule it came from — both stated at the top of this document. Neither is an opinion; that is the difference.

---

No baseline was promoted, and none can be: `promote` is absent from the operator's surface by construction. A baseline is an approved reference, and the approval is a person's.

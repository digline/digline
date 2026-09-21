"""Re-retrieve, and write the passages back into `cases.json`.

Run this when the corpus or the retriever has deliberately changed and you want
the cases to follow:

    uv run python freeze.py

It is a separate command on purpose. The suite reads the passages and never
calls the retriever, so retrieval moves only when somebody asks it to, and the
asking leaves a diff in `cases.json` that review can see. A suite that
re-retrieved at import would move its own inputs on every run while claiming
the retrieval was frozen — which is what this example used to do.

The `Faithfulness` scores are only as comparable as the passages under them, so
a run of this script is the start of a new baseline, not a no-op.
"""

from __future__ import annotations

import json
from pathlib import Path

import app

HERE = Path(__file__).parent
CASES = HERE / "cases.json"


def main() -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    for case in cases:
        case["context"] = app.retrieve(case["question"])
    CASES.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"froze {len(cases)} cases into {CASES.name}")


if __name__ == "__main__":
    main()

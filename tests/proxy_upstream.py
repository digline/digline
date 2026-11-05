"""The fake OpenAI and Anthropic of `tests/test_record_proxy.py`, as a process:
what the CI job `through-the-proxy` puts behind `digline record proxy`, so the
clients of other languages meet the same upstream the proxy's own tests do.

    python -m tests.proxy_upstream PORT

Serves on `127.0.0.1:PORT` until it is stopped, and says so on one line once
it listens.
"""

from __future__ import annotations

import sys
import threading

from tests.test_record_proxy import Upstream


def main(argv: list[str]) -> None:
    fake = Upstream(port=int(argv[0]))
    print(f"fake upstream listening on {fake.address}", flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main(sys.argv[1:])

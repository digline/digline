"""Write the fixtures a recorder in another language is held to, from digline's
own Python code. (ADR 0062 §2, §4)

    uv run python recorders/fixtures/make.py

Every file here is digline's answer to a fixed question: what a setup's
digest is, how a float is written, what a switch file says, what the store
lays out, and the bytes of one recorded call. `tests/test_recorder_fixtures.py`
runs `expected()` and holds each file equal to it, so a change on the Python
side that moves an answer turns that test red until this script is run again;
the Java tests read the same files and hold `DiglineRecorder.java` to them.
"""

from __future__ import annotations

import json
import math
import random
import struct
import tempfile
from decimal import ROUND_HALF_EVEN, Context, Decimal
from pathlib import Path
from typing import Any

from digline.core import Usage
from digline.core.recording import Recording, float_text, input_of, setup_digest_of
from digline.recorder import RecorderStartError, parse_switch
from digline.run.driver import Response, recorded
from digline.store.file_store import (
    _GITATTRIBUTES,  # pyright: ignore[reportPrivateUsage]
    _GITIGNORE,  # pyright: ignore[reportPrivateUsage]
    FileResultStore,
    RecordingWriter,
)
from digline.targets import Completion, ToolCall

HERE = Path(__file__).resolve().parent

#: The setups whose digests are fixed. The first is the one measured across
#: Java and Python on 2026-11-04, `81869b20f0d8875a` (ADR 0062, *What was
#: measured*).
SETUPS: list[dict[str, Any]] = [
    {"max_tokens": 64, "model": "claude-haiku-4-5"},
    {"model": "gpt-4o-mini", "temperature": 0.2},
    {
        "model": "gpt-4o-mini",
        "temperature": 0.7,
        "top_p": 1.0,
        "frequency_penalty": 1e-05,
        "presence_penalty": -0.0,
        "logit_scale": 1e16,
        "seed": 12345678901234567890,
        "stop": ["\n\n", "Fin."],
        "system": [
            {"role": "system", "content": "Réponds en français, brièvement. 😀"}
        ],
        "tools": [
            {"type": "function", "function": {"name": "lookup", "parameters": {}}}
        ],
        "response_format": None,
        "logprobs": False,
        "Zeta": 1,
        "ä": 2,
        # DEL is ASCII and escaped only in the digest's text, and U+0080 is not.
        "delete": "\x7f\x80",
    },
]

#: Floats whose text is fixed, beside the random ones below.
EDGES: list[float] = [
    0.0,
    -0.0,
    0.1,
    0.2,
    0.7,
    1.0,
    -1.5,
    100.0,
    1e-05,
    0.0001,
    0.001,
    123456789.123,
    1e15,
    1e16,
    1e22,
    1e23,
    9007199254740993.0,
    0.30000000000000004,
    1 / 3,
    2 / 3,
    812.3456789,
    5e-324,
    2.2250738585072014e-308,
    1.7976931348623157e308,
]


def _far_from_nearest() -> list[float]:
    """The powers of two, and their neighbours, whose `repr` is not the
    decimal of its length nearest to them: there the decimal nearest does not
    read back, and a shorter search than Python's finds a longer text."""
    found: list[float] = []
    for exponent in range(-1074, 1024):
        power = math.ldexp(1.0, exponent)
        for value in (power, math.nextafter(power, 0), math.nextafter(power, math.inf)):
            if not value or not math.isfinite(value):
                continue
            written = Decimal(repr(value)).normalize()
            length = len(written.as_tuple().digits)
            nearest = Context(prec=length, rounding=ROUND_HALF_EVEN).plus(
                Decimal(value)
            )
            if float(nearest) != value:
                found.append(value)
    return found


def _floats() -> list[list[str]]:
    """Every edge, the powers of two whose text is not the nearest decimal,
    then random doubles: any bit pattern that is finite, and decimals of a few
    digits, which is what a parameter usually is. Each row is the double's
    bits, its `repr`, its `float_text`, and the `repr` of it rounded to six
    places, as a document keeps a number."""
    draw = random.Random(20261105)
    values = [*EDGES, *_far_from_nearest()]
    for _ in range(500):
        value = math.nan
        while not math.isfinite(value):
            (value,) = struct.unpack("<d", draw.getrandbits(64).to_bytes(8, "little"))
        values.append(value)
    for _ in range(500):
        values.append(round(draw.uniform(-1000, 1000), draw.randint(0, 9)))
    return [
        [
            struct.pack(">d", value).hex(),
            repr(value),
            float_text(value),
            repr(round(value, 6)),
        ]
        for value in values
    ]


#: Switch files and the regime each is read in. The sentence `parse_switch`
#: refuses one with is fixed, and the Java reader is held to it word for word.
SWITCHES: list[tuple[str, bool]] = [
    ("on = true\n", False),
    ("on = false\n", True),
    (
        'on = true\nsample = 0.25\nredact = "none"\nceiling = 1048576\ninterval = 2\n',
        True,
    ),
    ("on = true\n", True),
    ("on = true\nsample = 0.5\n", True),
    ("on = true\nproduction = true\n", False),
    ("on = maybe\n", False),
    ("on = true\ncolour = 1\nzz = 2\n", False),
    ("sample = 0.5\n", False),
    ("on = 1\n", False),
    ("on = true\nsample = 0\n", False),
    ("on = true\nsample = 1.5\n", False),
    ("on = true\nsample = true\n", False),
    ("on = true\nsample = nan\n", False),
    ("on = true\nsample = 1\n", False),
    ('on = true\nredact = "names"\n', False),
    ('on = true\nredact = "it\'s"\n', False),
    ("on = true\nredact = 5\n", False),
    ('on = true\nredact = "' + "x" * 50 + '"\n', False),
    ("on = true\nceiling = 0\n", False),
    ("on = true\nceiling = 1.5\n", False),
    ("on = true\nceiling = 1_000_000\n", False),
    ("on = true\ninterval = 0\n", False),
    ("on = true\ninterval = 0.5\n", False),
    ("on = true\nproduction = 1\n", False),
    ("# the switch\non = false # off for now\n\n", False),
    ("on = true\n[table]\nkey = 1\n", False),
    ("on = true\non = false\n", False),
    ("", False),
]


def _switches() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for text, production in SWITCHES:
        entry: dict[str, Any] = {"text": text, "production": production}
        try:
            switch = parse_switch(text, where="recorder.toml", production=production)
        except RecorderStartError as exc:
            entry["refusal"] = str(exc)
        else:
            entry["switch"] = {
                "on": switch.on,
                "sample": switch.sample,
                "ceiling": switch.ceiling,
                "interval": switch.interval,
                "production": switch.production,
                "declared": sorted(switch.declared),
            }
        found.append(entry)
    return found


#: One recorded call, as a hook hands it to the writer.
CALL: dict[str, Any] = {
    "tenant": "acme",
    "app": "support",
    "suite": "refunds",
    "recorded_at": "2026-11-05T08:00:00.123456+00:00",
    "case": {
        "messages": [
            {
                "role": "user",
                "content": 'Où est mon remboursement ? 100 €, "vite"\n😀   \x7f',
            }
        ]
    },
    "setup": SETUPS[2],
    "output": "Il a été envoyé lundi.",
    "latency_ms": 812.3456789,
    "usage": {
        "input_tokens": 14,
        "output_tokens": 7,
        "cache_read_tokens": 3,
        "cache_write_tokens": 0,
        "thinking_tokens": 0,
    },
    "finish": "tool_use",
    "tool_calls": [
        {"tool": "lookup", "arguments": {"order": "A1", "weight": 0.1234567, "n": 2}},
        {"tool": None, "arguments": "not json"},
    ],
}


def _call_bytes() -> str:
    """The file digline's own writer writes for `CALL`, through the path a
    wrapped client's call takes: a `Completion`, its metadata, `recorded()`,
    a `Recording`, and the `RecordingWriter`."""
    usage = Usage(**CALL["usage"])
    completion = Completion(
        text=CALL["output"],
        usage=usage,
        finish=CALL["finish"],
        tools=tuple(call["tool"] for call in CALL["tool_calls"]),
        tool_calls=tuple(
            ToolCall(
                tool=call["tool"],
                arguments=call["arguments"],
                status="not_reported",
                result_absence="not_reported",
            )
            for call in CALL["tool_calls"]
        ),
    )
    response = recorded(
        Response(
            output=CALL["output"],
            input=input_of(CALL["case"]["messages"]),
            latency_ms=CALL["latency_ms"],
            usage=usage,
            metadata=completion.as_metadata(),
        )
    )
    recording = Recording(
        source_tenant=CALL["tenant"],
        app=CALL["app"],
        suite=CALL["suite"],
        case=CALL["case"],
        setup=CALL["setup"],
        setup_digest=setup_digest_of(CALL["setup"]),
        response=response,
        recorded_at=CALL["recorded_at"],
    )
    with tempfile.TemporaryDirectory() as scratch:
        path = RecordingWriter(FileResultStore(Path(scratch))).write(recording)
        return path.read_text(encoding="utf-8")


def _json(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def expected() -> dict[str, str]:
    """Each fixture's path, relative to this directory, and its text."""
    return {
        "setups.json": _json(
            [{"setup": setup, "digest": setup_digest_of(setup)} for setup in SETUPS]
        ),
        "floats.json": "[\n"
        + ",\n".join(json.dumps(row) for row in _floats())
        + "\n]\n",
        "switches.json": _json(_switches()),
        "call.json": _json(CALL),
        "call.expected.json": _call_bytes(),
        "layout/gitignore": _GITIGNORE,
        "layout/gitattributes": _GITATTRIBUTES,
    }


if __name__ == "__main__":
    for name, text in expected().items():
        target = HERE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"wrote {target.relative_to(HERE)}")

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

import base64
import json
import math
import random
import struct
import tempfile
import zlib
from decimal import ROUND_HALF_EVEN, Context, Decimal
from pathlib import Path
from typing import Any, cast

from digline.core import Usage
from digline.core.recording import Recording, float_text, input_of, setup_digest_of
from digline.recorder import RecorderStartError, parse_switch
from digline.run.driver import Response, recorded
from digline.store.file_store import (
    _GITATTRIBUTES,  # pyright: ignore[reportPrivateUsage]
    _GITIGNORE,  # pyright: ignore[reportPrivateUsage]
    FileResultStore,
    RecordingWriter,
    checked_name,
)
from digline.store.protocol import PathRefusedError
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
    wrapped client's call takes: a `Completion`, then `_written`."""
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
    return _written(
        case=CALL["case"],
        setup=CALL["setup"],
        completion=completion,
        latency_ms=CALL["latency_ms"],
    )


#: The wire's calls, one per provider and shape, as the HTTP carries them:
#: the request's JSON body and the reply's, or the reply's events in order. A
#: hook reads these off its client's HTTP, and the file it writes is held to
#: the one each provider's own map writes from the same bytes: read as
#: `digline record proxy` reads OpenAI and Anthropic (`digline.recording_wire`),
#: and Bedrock as boto3 hands it over, `modelId` from the path beside the body
#: and each event as `{type: payload}`. The proxy's own reading of the Bedrock
#: calls is held to the same files in `tests/test_recorder_java.py`. No
#: `extra_body` case: on the wire its keys are in the body like any other, so
#: a hook reads them as it reads the rest, and the in-process maps merge it the
#: same way since #919 (`tests/test_recorder_extra_body.py`).
def _chunk(event: dict[str, Any]) -> dict[str, Any]:
    """A Messages event as InvokeModelWithResponseStream carries it: its JSON
    in base64, under `chunk.bytes`."""
    data = json.dumps(event, separators=(",", ":")).encode("utf-8")
    return {"chunk": {"bytes": base64.b64encode(data).decode("ascii")}}


WIRE_CALLS: dict[str, dict[str, Any]] = {
    "openai-single": {
        "route": "openai",
        "path": "/v1/chat/completions",
        "request": {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "Answer in one line."},
                {"role": "user", "content": "Où est la commande A1 ?"},
            ],
            "temperature": 0.2,
            "max_tokens": 64,
            "user": "customer-42",
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "parameters": {
                            "type": "object",
                            "properties": {"order": {"type": "string"}},
                        },
                    },
                }
            ],
        },
        "reply": {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 1762329600,
            "model": "gpt-4o-mini-2024-07-18",
            "system_fingerprint": "fp_1",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": "Je regarde.",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "lookup",
                                    "arguments": '{"order": "A1", "weight": 1.5}',
                                },
                            },
                            {
                                "id": "call_2",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "A2?"},
                            },
                        ],
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 40,
                "completion_tokens": 12,
                "total_tokens": 52,
                "prompt_tokens_details": {"cached_tokens": 8},
                "completion_tokens_details": {"reasoning_tokens": 0},
            },
        },
    },
    "openai-stream": {
        "route": "openai",
        "path": "/v1/chat/completions",
        "request": {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Where is A1?"}],
            "stream": True,
            "stream_options": {"include_usage": True},
        },
        "events": [
            {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": 1762329600,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": ""},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": 1762329600,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "It left "},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": 1762329600,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "on Monday."},
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": 1762329600,
                "model": "gpt-4o-mini",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            },
            {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": 1762329600,
                "model": "gpt-4o-mini",
                "choices": [],
                "usage": {
                    "prompt_tokens": 9,
                    "completion_tokens": 5,
                    "total_tokens": 14,
                },
            },
        ],
    },
    "openai-stream-tool": {
        "route": "openai",
        "path": "/v1/chat/completions",
        "request": {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Where is A1?"}],
            "stream": True,
        },
        "events": [
            {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": 1762329600,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "lookup", "arguments": ""},
                                }
                            ],
                        },
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": 1762329600,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": '{"order":'}}
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": 1762329600,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": ' "A1"}'}}
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            },
            {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": 1762329600,
                "model": "gpt-4o-mini",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
            },
        ],
    },
    "anthropic-single": {
        "route": "anthropic",
        "path": "/v1/messages",
        "request": {
            "model": "claude-haiku-4-5",
            "max_tokens": 256,
            "system": "Answer in one line.",
            "metadata": {"user_id": "customer-42"},
            "temperature": 0.5,
            "messages": [{"role": "user", "content": "Où est la commande A1 ?"}],
        },
        "reply": {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-4-5-20251001",
            "content": [
                {"type": "text", "text": "Je regarde. "},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "lookup",
                    "input": {"order": "A1", "weight": 0.1234567},
                },
                {"type": "text", "text": "Un instant."},
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {
                "input_tokens": 30,
                "output_tokens": 20,
                "cache_read_input_tokens": 100,
                "cache_creation_input_tokens": 0,
            },
        },
    },
    "anthropic-stream": {
        "route": "anthropic",
        "path": "/v1/messages",
        "request": {
            "model": "claude-haiku-4-5",
            "max_tokens": 256,
            "stream": True,
            "messages": [{"role": "user", "content": "Where is A1?"}],
        },
        "events": [
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-haiku-4-5-20251001",
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 12, "output_tokens": 1},
                },
            },
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "Looking "},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "it up."},
            },
            {"type": "content_block_stop", "index": 0},
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "lookup",
                    "input": {},
                },
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '{"order": '},
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '"A1"}'},
            },
            {"type": "content_block_stop", "index": 1},
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                "usage": {"output_tokens": 18},
            },
            {"type": "message_stop"},
        ],
    },
    "bedrock-single": {
        "route": "bedrock",
        "path": "/model/anthropic.claude-3-5-haiku-20241022-v1%3A0/converse",
        "model_id": "anthropic.claude-3-5-haiku-20241022-v1:0",
        "request": {
            "messages": [
                {"role": "user", "content": [{"text": "Où est la commande A1 ?"}]}
            ],
            "system": [{"text": "Answer in one line."}],
            "inferenceConfig": {"maxTokens": 256, "temperature": 0.2},
            "requestMetadata": {"customer": "42"},
        },
        "reply": {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"text": "Je regarde."},
                        {
                            "toolUse": {
                                "toolUseId": "t1",
                                "name": "lookup",
                                "input": {"order": "A1"},
                            }
                        },
                    ],
                }
            },
            "stopReason": "tool_use",
            "usage": {
                "inputTokens": 30,
                "outputTokens": 12,
                "totalTokens": 142,
                "cacheReadInputTokens": 100,
            },
            "metrics": {"latencyMs": 300},
        },
    },
    "bedrock-stream": {
        "route": "bedrock",
        "path": "/model/anthropic.claude-3-5-haiku-20241022-v1%3A0/converse-stream",
        "model_id": "anthropic.claude-3-5-haiku-20241022-v1:0",
        "request": {
            "messages": [{"role": "user", "content": [{"text": "Where is A1?"}]}],
            "inferenceConfig": {"maxTokens": 256},
        },
        "events": [
            {"messageStart": {"role": "assistant"}},
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"text": "Looking "},
                }
            },
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"text": "it up."},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {
                "contentBlockStart": {
                    "contentBlockIndex": 1,
                    "start": {"toolUse": {"toolUseId": "t1", "name": "lookup"}},
                }
            },
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 1,
                    "delta": {"toolUse": {"input": '{"order": '}},
                }
            },
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 1,
                    "delta": {"toolUse": {"input": '"A1"}'}},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 1}},
            {"messageStop": {"stopReason": "tool_use"}},
            {
                "metadata": {
                    "usage": {"inputTokens": 12, "outputTokens": 18, "totalTokens": 30},
                    "metrics": {"latencyMs": 400},
                }
            },
        ],
    },
    # InvokeModel with an Anthropic model: the body is Anthropic's Messages,
    # read with the map a direct Messages call is read with (P-1541, P-1543).
    # `metadata` is in the body and out of the setup, as Anthropic's map has it.
    "bedrock-invoke": {
        "route": "bedrock",
        "path": "/model/anthropic.claude-3-5-haiku-20241022-v1%3A0/invoke",
        "model_id": "anthropic.claude-3-5-haiku-20241022-v1:0",
        "request": {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 256,
            "system": "Answer in one line.",
            "messages": [{"role": "user", "content": "Où est la commande A1 ?"}],
            "metadata": {"user_id": "customer-42"},
        },
        "reply": {
            "id": "msg_bedrock_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-3-5-haiku-20241022",
            "content": [
                {"type": "text", "text": "Je regarde."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "lookup",
                    "input": {"order": "A1"},
                },
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {"input_tokens": 30, "output_tokens": 12},
        },
    },
    # Its stream: each event a `chunk` whose `bytes` carry a Messages event in
    # base64, as Bedrock sends it and the proxy and the Java hook read it.
    "bedrock-invoke-stream": {
        "route": "bedrock",
        "path": (
            "/model/us.anthropic.claude-3-5-haiku-20241022-v1%3A0"
            "/invoke-with-response-stream"
        ),
        "model_id": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
        "request": {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 256,
            "messages": [{"role": "user", "content": "Where is A1?"}],
        },
        "events": [
            _chunk(event)
            for event in cast(
                "tuple[dict[str, Any], ...]",
                (
                    {
                        "type": "message_start",
                        "message": {
                            "id": "msg_bedrock_2",
                            "type": "message",
                            "role": "assistant",
                            "model": "claude-3-5-haiku-20241022",
                            "content": [],
                            "stop_reason": None,
                            "stop_sequence": None,
                            "usage": {"input_tokens": 12, "output_tokens": 1},
                        },
                    },
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "text", "text": ""},
                    },
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": "Looking it up."},
                    },
                    {"type": "content_block_stop", "index": 0},
                    {
                        "type": "content_block_start",
                        "index": 1,
                        "content_block": {
                            "type": "tool_use",
                            "id": "toolu_2",
                            "name": "lookup",
                            "input": {},
                        },
                    },
                    {
                        "type": "content_block_delta",
                        "index": 1,
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": '{"order": "A1"}',
                        },
                    },
                    {"type": "content_block_stop", "index": 1},
                    {
                        "type": "message_delta",
                        "delta": {"stop_reason": "tool_use", "stop_sequence": None},
                        "usage": {"output_tokens": 18},
                    },
                    {"type": "message_stop"},
                ),
            )
        ],
    },
    "openai-refusal": {
        "route": "openai",
        "path": "/v1/chat/completions",
        "request": {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Tell me a secret."}],
        },
        "reply": {
            "id": "chatcmpl-2",
            "object": "chat.completion",
            "created": 1762329600,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "refusal": "I can't help with that.",
                    },
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 6, "total_tokens": 15},
        },
    },
    "anthropic-server-tool": {
        "route": "anthropic",
        "path": "/v1/messages",
        "request": {
            "model": "claude-haiku-4-5",
            "max_tokens": 256,
            "messages": [{"role": "user", "content": "Search twice."}],
        },
        "reply": {
            "id": "msg_2",
            "type": "message",
            "role": "assistant",
            "model": "claude-haiku-4-5-20251001",
            "content": [
                {
                    "type": "server_tool_use",
                    "id": "srv_1",
                    "name": "web_search",
                    "input": {"query": "A1"},
                },
                {
                    "type": "web_search_tool_result",
                    "tool_use_id": "srv_1",
                    "content": {
                        "type": "web_search_tool_result_error",
                        "error_code": "max_uses_exceeded",
                    },
                },
                {
                    "type": "server_tool_use",
                    "id": "srv_2",
                    "name": "web_search",
                    "input": {"query": "A2"},
                },
                {
                    "type": "web_search_tool_result",
                    "tool_use_id": "srv_2",
                    "content": [
                        {
                            "type": "web_search_result",
                            "url": "https://example.com",
                            "title": "A2",
                            "encrypted_content": "x",
                        }
                    ],
                },
                {"type": "tool_use", "id": "toolu_1", "input": {"order": "A1"}},
                {"type": "text", "text": "Done."},
            ],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": 30,
                "output_tokens": 20,
                "output_tokens_details": {"thinking_tokens": 4},
            },
        },
    },
    "bedrock-server-tool": {
        "route": "bedrock",
        "path": "/model/amazon.nova-pro-v1%3A0/converse",
        "model_id": "amazon.nova-pro-v1:0",
        "request": {
            "messages": [{"role": "user", "content": [{"text": "Search twice."}]}],
        },
        "reply": {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": "s1",
                                "name": "search",
                                "type": "server_tool_use",
                                "input": {"q": "A1"},
                            }
                        },
                        {
                            "toolResult": {
                                "toolUseId": "s1",
                                "status": "error",
                                "content": [
                                    {"text": "quota"},
                                    {"json": {"code": 429, "ratio": 0.33333333}},
                                ],
                            }
                        },
                        {
                            "toolUse": {
                                "toolUseId": "s2",
                                "name": "search",
                                "type": "server_tool_use",
                                "input": ["A2"],
                            }
                        },
                        {"toolResult": {"toolUseId": "s2", "content": [{"text": "x"}]}},
                        {"toolUse": {"toolUseId": "t3", "input": {"order": "A1"}}},
                        {"text": "Done."},
                    ],
                }
            },
            "stopReason": "end_turn",
            "usage": {"inputTokens": 30, "outputTokens": 12, "totalTokens": 42},
        },
    },
}

#: What every wire call's recording carries beside what the call decides.
WIRE_LATENCY_MS = 250.5


def _wire_completion(call: dict[str, Any]) -> tuple[dict[str, Any], Any, Any]:
    """The request as the provider's map reads it, the map, and the
    completion it reads from the reply or the events."""
    route = call["route"]
    if route == "bedrock" and "/invoke" in call["path"]:
        from digline_bedrock.recording import INVOKE_MAP, INVOKE_STREAM_MAP

        request = {"modelId": call["model_id"], "body": call["request"]}
        if "events" in call:
            reading = INVOKE_STREAM_MAP.reading(request)
            for event in call["events"]:
                # As boto3 hands a chunk over: its bytes decoded.
                raw = base64.b64decode(event["chunk"]["bytes"])
                reading.add({"chunk": {"bytes": raw}})
            return request, INVOKE_STREAM_MAP, reading.completion(None)
        return request, INVOKE_MAP, INVOKE_MAP.completion(call["reply"], request)
    if route == "bedrock":
        from digline_bedrock.recording import MAP as BEDROCK
        from digline_bedrock.recording import STREAM_MAP as BEDROCK_STREAM

        request = {"modelId": call["model_id"], **call["request"]}
        if "events" in call:
            reading = BEDROCK_STREAM.reading(request)
            for event in call["events"]:
                reading.add(event)
            return request, BEDROCK_STREAM, reading.completion(None)
        return request, BEDROCK, BEDROCK.completion(call["reply"], request)
    if route == "openai":
        from digline_openai.recording import WIRE
    else:
        from digline_anthropic.recording import WIRE
    request = dict(call["request"])
    mapped: Any = WIRE.map
    if "events" in call:
        reading = mapped.reading(request)
        for event in call["events"]:
            reading.add(WIRE.event(event))
        return request, mapped, reading.completion(None)
    return request, mapped, mapped.completion(WIRE.reply(call["reply"]), request)


def _wire_bytes(call: dict[str, Any]) -> str:
    """The file digline's recorder writes for one wire call: the map's split
    and completion, then `_record`'s path to the writer."""
    request, mapped, completion = _wire_completion(call)
    case, setup = mapped.split(request)
    return _written(
        case=case,
        setup=setup,
        completion=completion,
        latency_ms=WIRE_LATENCY_MS,
    )


def _written(
    *,
    case: dict[str, Any],
    setup: dict[str, Any],
    completion: Completion,
    latency_ms: float,
) -> str:
    """One call's file, through the path `_record` takes: the metadata of its
    completion, `recorded()`, a `Recording`, and the `RecordingWriter`."""
    messages = case.get("messages")
    response = recorded(
        Response(
            output=completion.text,
            input=None if messages is None else input_of(messages),
            latency_ms=latency_ms,
            usage=completion.usage,
            metadata=completion.as_metadata(),
        )
    )
    recording = Recording(
        source_tenant=CALL["tenant"],
        app=CALL["app"],
        suite=CALL["suite"],
        case=case,
        setup=setup,
        setup_digest=setup_digest_of(setup),
        response=response,
        recorded_at=CALL["recorded_at"],
    )
    with tempfile.TemporaryDirectory() as scratch:
        path = RecordingWriter(FileResultStore(Path(scratch))).write(recording)
        return path.read_text(encoding="utf-8")


#: AWS's event stream, as Bedrock's two streams reply in it: the bytes a
#: reader of the framing is held to, each file's checksums by zlib's CRC-32,
#: and `eventstream/frames.json` saying what botocore, the decoder boto3 and
#: `digline record proxy` read them with, makes of each. A header of every
#: type that is not a string is in `one-event`, which Bedrock does not send
#: and the framing allows.
def _header(name: str, kind: int, value: bytes) -> bytes:
    key = name.encode("utf-8")
    return bytes([len(key)]) + key + bytes([kind]) + value


def _string(name: str, value: str) -> bytes:
    text = value.encode("utf-8")
    return _header(name, 7, struct.pack(">H", len(text)) + text)


def _frame(
    kind: str, payload: object, *, exception: bool = False, extra: bytes = b""
) -> bytes:
    """One message: the prelude and its CRC, the headers, the payload and
    the message's CRC."""
    headers = extra + (
        _string(":exception-type", kind)
        + _string(":content-type", "application/json")
        + _string(":message-type", "exception")
        if exception
        else _string(":event-type", kind)
        + _string(":content-type", "application/json")
        + _string(":message-type", "event")
    )
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    prelude = struct.pack(">II", 12 + len(headers) + len(body) + 4, len(headers))
    message = prelude + struct.pack(">I", zlib.crc32(prelude)) + headers + body
    return message + struct.pack(">I", zlib.crc32(message))


def _frames(events: list[dict[str, Any]]) -> bytes:
    return b"".join(
        _frame(kind, payload) for event in events for kind, payload in event.items()
    )


#: Every type of header value that is not a string, with a value of its own.
_OTHER_HEADERS = (
    _header("true", 0, b"")
    + _header("false", 1, b"")
    + _header("byte", 2, b"\x07")
    + _header("short", 3, struct.pack(">h", -2))
    + _header("integer", 4, struct.pack(">i", 1 << 20))
    + _header("long", 5, struct.pack(">q", 1 << 40))
    + _header("bytes", 6, struct.pack(">H", 3) + b"\x00\x01\x02")
    + _header("timestamp", 8, struct.pack(">q", 1762387200000))
    + _header("uuid", 9, bytes(range(16)))
)

_TOOL_USE: list[dict[str, Any]] = [
    {
        "contentBlockStart": {
            "contentBlockIndex": 0,
            "start": {"toolUse": {"toolUseId": "t1", "name": "lookup"}},
        }
    },
    {
        "contentBlockDelta": {
            "contentBlockIndex": 0,
            "delta": {"toolUse": {"input": '{"order": "A1"}'}},
        }
    },
    {"messageStop": {"stopReason": "tool_use"}},
]


def _flipped(data: bytes, at: int) -> bytes:
    return data[:at] + bytes([data[at] ^ 0xFF]) + data[at + 1 :]


def _eventstreams() -> dict[str, bytes]:
    """Each file of `eventstream/`, by its name."""
    tool_use = _frames(_TOOL_USE)
    first = len(_frame(*next(iter(_TOOL_USE[0].items()))))
    second = len(_frame(*next(iter(_TOOL_USE[1].items()))))
    return {
        "one-event": _frame(
            "messageStart", {"role": "assistant"}, extra=_OTHER_HEADERS
        ),
        "tool-use": tool_use,
        # Cut halfway through the second event: the first is read.
        "abandoned": tool_use[: first + second // 2],
        # The second event's last byte of payload changed, its CRC kept.
        "bad-crc": _flipped(tool_use, first + second - 5),
        # The first event's total length changed, its prelude's CRC kept.
        "bad-prelude": _flipped(tool_use, 3),
        "exception": _frame("messageStart", {"role": "assistant"})
        + _frame("throttlingException", {"message": "slow down"}, exception=True),
        "bedrock-stream": _frames(WIRE_CALLS["bedrock-stream"]["events"]),
        "bedrock-invoke-stream": _frames(WIRE_CALLS["bedrock-invoke-stream"]["events"]),
    }


def _read_by_botocore(data: bytes) -> dict[str, Any]:
    """What botocore makes of the bytes: the events, each `{type: payload}`,
    and whether bytes are left over that hold no whole message; or that it
    refuses them, a checksum or an exception."""
    from botocore.eventstream import (  # pyright: ignore[reportMissingTypeStubs]
        EventStreamBuffer,
        ParserError,
    )

    buffer: Any = EventStreamBuffer()
    buffer.add_data(data)
    events: list[object] = []
    used = 0
    try:
        for message in buffer:
            headers = cast(dict[str, object], message.headers)
            if headers.get(":message-type") != "event":
                return {"refused": "exception"}
            payload = cast(bytes, message.payload)
            events.append(
                {str(headers[":event-type"]): json.loads(payload) if payload else {}}
            )
            used += message.prelude.total_length
    except ParserError:
        return {"refused": "checksum"}
    return {"events": events, "cut": used != len(data)}


#: The gate's markers a writer may find in `.digline/<tenant>/runs/.gate/`,
#: each with its age in seconds, far from `STALE_SECONDS` on either side so
#: the second a test takes cannot move it across. (ADR 0058, 2026-11-05)
_KEY = "2026-11-05T12-30-00-123456-00-00-0123456789abcdef"
_OTHER = "2026-11-05T12-31-00-000001-00-00-fedcba9876543210"


def _marker(run_id: object, age: int, name: str = "") -> dict[str, Any]:
    text = json.dumps(
        {"run_id": run_id, "pid": 4242, "started_at": "x", "suite": "refunds"}
    )
    return {"name": name or f"4242-{run_id}.json", "text": text, "age": age}


GATES: list[list[dict[str, Any]]] = [
    [],
    [_marker(_KEY, 10)],
    [_marker(_KEY, 1000)],
    [_marker(_KEY, 10), _marker(_OTHER, 10, "4343-other.json")],
    [_marker(_KEY, 10), _marker(_OTHER, 1000, "4343-other.json")],
    [{"name": "4242-x.json", "text": "not JSON", "age": 10}],
    [{"name": "4242-x.json", "text": "[]", "age": 10}],
    [_marker("", 10, "4242-x.json")],
    [_marker(7, 10, "4242-x.json")],
    [_marker(_KEY, 10, f".4242-{_KEY}.json.partial")],
    [_marker(_KEY, 10, f".4242-{_KEY}.json")],
    [_marker(_KEY, 10, f"4242-{_KEY}.txt")],
]


def _gates() -> list[dict[str, Any]]:
    """What `digline.recorder._gate` answers for each set of markers, laid
    out in a scratch directory with each file's time set back by its age."""
    import os
    import time

    from digline.host.gate import GATE_DIRECTORY
    from digline.recorder import _gate  # pyright: ignore[reportPrivateUsage]

    rows: list[dict[str, Any]] = []
    for markers in GATES:
        with tempfile.TemporaryDirectory() as scratch:
            place = Path(scratch, ".digline", "acme", *GATE_DIRECTORY)
            place.mkdir(parents=True)
            now = time.time()
            for marker in markers:
                path = place / marker["name"]
                path.write_text(marker["text"], encoding="utf-8")
                os.utime(path, (now - marker["age"], now - marker["age"]))
            origin, run_id = _gate(Path(scratch), "acme")
        rows.append({"markers": markers, "origin": origin, "run_id": run_id})
    return rows


#: Names a tenant may and may not be, and the store's sentence for each it
#: refuses: what `checked_name` answers, which the Java writer is held to.
NAMES: list[str] = [
    "acme",
    "acme-2",
    "a.b_c",
    "9lives",
    "",
    ".",
    "..",
    "../x",
    "a/b",
    "a\\b",
    "acme\n",
    "acme\r",
    "\nacme",
    "_unassigned",
    "-x",
    "a b",
    "é",
    "x" * 50,
]


def _names() -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for name in NAMES:
        try:
            checked_name(name, "tenant")
        except PathRefusedError as exc:
            found.append({"name": name, "refusal": str(exc)})
        else:
            found.append({"name": name, "refusal": None})
    return found


def _json(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def expected() -> dict[str, str | bytes]:
    """Each fixture's path, relative to this directory, and its text, or its
    bytes for an event stream."""
    return {
        "setups.json": _json(
            [{"setup": setup, "digest": setup_digest_of(setup)} for setup in SETUPS]
        ),
        "floats.json": "[\n"
        + ",\n".join(json.dumps(row) for row in _floats())
        + "\n]\n",
        "switches.json": _json(_switches()),
        "gates.json": _json(_gates()),
        "call.json": _json(CALL),
        "call.expected.json": _call_bytes(),
        "names.json": _json(_names()),
        "layout/gitignore": _GITIGNORE,
        "layout/gitattributes": _GITATTRIBUTES,
        **{f"wire/{name}.json": _json(call) for name, call in WIRE_CALLS.items()},
        **{
            f"wire/{name}.expected.json": _wire_bytes(call)
            for name, call in WIRE_CALLS.items()
        },
        **{f"eventstream/{name}.bin": data for name, data in _eventstreams().items()},
        "eventstream/frames.json": _json(
            {name: _read_by_botocore(data) for name, data in _eventstreams().items()}
        ),
    }


if __name__ == "__main__":
    for name, text in expected().items():
        target = HERE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            target.write_bytes(text)
        else:
            target.write_text(text, encoding="utf-8")
        print(f"wrote {target.relative_to(HERE)}")

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
#: `extra_body`: an in-process map keeps it as a key of its own and the wire
#: merges it (RELEASING.md, *Owed to the next version*).
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
        "names.json": _json(_names()),
        "layout/gitignore": _GITIGNORE,
        "layout/gitattributes": _GITATTRIBUTES,
        **{f"wire/{name}.json": _json(call) for name, call in WIRE_CALLS.items()},
        **{
            f"wire/{name}.expected.json": _wire_bytes(call)
            for name, call in WIRE_CALLS.items()
        },
    }


if __name__ == "__main__":
    for name, text in expected().items():
        target = HERE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        print(f"wrote {target.relative_to(HERE)}")

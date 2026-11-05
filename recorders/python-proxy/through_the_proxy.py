"""The same calls as `recorders/node/through-the-proxy.mjs`, from Python's SDKs:
the CI job `through-the-proxy`'s positive control, whose recordings the other
languages' are compared with. The request is `recorders/through-the-proxy.json`.
"""

import json
import os
from pathlib import Path

import anthropic
import openai

proxy = os.environ["DIGLINE_PROXY"]
asked = json.loads(
    (Path(__file__).parent.parent / "through-the-proxy.json").read_text()
)
headers = {"X-Digline-Suite": asked["suite"], "X-Digline-App": "python"}
episode = {"X-Digline-Episode": "turn-python"}

chat = openai.OpenAI(
    base_url=f"{proxy}/v1", api_key="via-proxy", default_headers=headers
)
chat.chat.completions.create(**asked["openai"])
for _ in chat.chat.completions.create(**asked["openai"], stream=True):
    pass
chat.chat.completions.create(**asked["openai"], extra_headers=episode)
chat.chat.completions.create(**asked["openai"], extra_headers=episode)

messages = anthropic.Anthropic(
    base_url=proxy, api_key="via-proxy", default_headers=headers
)
messages.messages.create(**asked["anthropic"])
for _ in messages.messages.create(**asked["anthropic"], stream=True):
    pass

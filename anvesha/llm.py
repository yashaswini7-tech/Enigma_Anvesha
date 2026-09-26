"""One interface for the LLM: ollama (default, local) | anthropic (optional) | none.

Every prompt is passed through redact() here, so no caller can send raw identifiers.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Protocol

from anvesha import config
from anvesha.privacy.redact import redact


class LLMClient(Protocol):
    name: str
    model: str

    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str: ...


class OllamaClient:
    name = "ollama"

    def __init__(self, model: str = config.OLLAMA_MODEL, url: str = config.OLLAMA_URL) -> None:
        self.model, self.url = model, url.rstrip("/")

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/api/tags", timeout=3) as r:
                models = [m["name"] for m in json.load(r).get("models", [])]
            return any(m == self.model or m.startswith(f"{self.model}:") for m in models)
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str:
        body = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "seed": 7},
        }
        if json_mode:
            body["format"] = "json"
        req = urllib.request.Request(
            f"{self.url}/api/generate",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=config.LLM_TIMEOUT_S) as r:
            return json.load(r)["response"]


class AnthropicClient:
    name = "anthropic"

    def __init__(self, model: str = config.ANTHROPIC_MODEL) -> None:
        import anthropic

        self.model = model
        self._client = anthropic.Anthropic()

    def available(self) -> bool:
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def complete(self, system: str, prompt: str, json_mode: bool = False) -> str:
        if json_mode:
            system += "\nReply with one JSON object only."
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=400,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")


def get_client(provider: str | None = None, model: str | None = None) -> LLMClient | None:
    provider = provider or config.LLM_PROVIDER
    if provider == "ollama":
        client: LLMClient = OllamaClient(model or config.OLLAMA_MODEL)
    elif provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        client = AnthropicClient()
    else:
        return None
    return client if client.available() else None


def parse_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def complete_json(client: LLMClient, system: str, prompt: str) -> dict | None:
    return parse_json(client.complete(redact(system), redact(prompt), json_mode=True))


def complete_text(client: LLMClient, system: str, prompt: str) -> str:
    return client.complete(redact(system), redact(prompt)).strip()

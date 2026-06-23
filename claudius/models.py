"""Minimal OpenAI-compatible chat client.

One HTTP interface, many providers (OpenRouter, OpenAI, Together, Fireworks,
Groq, …) — the same idea as mini-SWE-agent's litellm layer, but dependency-free
(stdlib urllib only). Point `base_url` / `api_key_env` at whichever provider you
want; the wire format is the OpenAI Chat Completions schema.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


class ModelError(RuntimeError):
    pass


class Model:
    def __init__(self, *, name: str, base_url: str, api_key_env: str,
                 temperature: float = 0.0, max_tokens: int = 4096):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = os.environ.get(api_key_env)
        # Usage accounting (informational — the paper imposes no cost limit).
        self.n_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        if not self.api_key:
            raise ModelError(
                f"{api_key_env} is not set. Put it in claudius/.env (or the "
                f"sibling claudette/.env), or export it before running."
            )

    def query(self, messages: list[dict]) -> dict:
        payload = {
            "model": self.name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                # Optional OpenRouter attribution headers; harmless elsewhere.
                "HTTP-Referer": "https://github.com/frankbarrett/claudius",
                "X-Title": "claudius",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise ModelError(f"HTTP {exc.code} from provider: {detail}") from exc
        except urllib.error.URLError as exc:
            raise ModelError(f"Network error talking to provider: {exc}") from exc

        try:
            content = body["choices"][0]["message"].get("content") or ""
        except (KeyError, IndexError) as exc:
            raise ModelError(f"Unexpected response shape: {body}") from exc

        usage = body.get("usage") or {}
        self.n_calls += 1
        self.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
        self.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
        return {"content": content}

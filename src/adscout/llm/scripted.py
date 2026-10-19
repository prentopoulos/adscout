"""Scripted model answers for fake-mode runs on synthetic fixture companies.

A YAML file maps each role to each fixture company's answers, in order; the last answer
repeats when a role is asked more often. A request's role is the prompt its system text
starts with, and its domain is the fixture domain its messages mention first. An answer is
`data` (JSON returned as text), `text`, or raw `content` blocks, with optional usage counts.
Every number in a fake answer is scripted, never measured.
"""

import json
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from anthropic.types import Message

from adscout.config import ConfigError, load_yaml
from adscout.llm.adapter import ModelRequest
from adscout.llm.fakes import fake_message
from adscout.llm.prompts import load_prompt, roles

USAGE_KEYS = ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens")


class ScriptedModels:
    def __init__(self, path: Path) -> None:
        data = load_yaml(path)
        if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
            raise ConfigError(f"{path.name}: needs an `answers` mapping of role to domain")
        self.answers: dict[str, dict[str, list[dict[str, Any]]]] = data["answers"]
        unknown = sorted(set(self.answers) - set(roles()))
        if unknown:
            raise ConfigError(f"{path.name}: unknown roles {unknown}")
        self.prompts = {load_prompt(role).text: role for role in self.answers}
        self.asked: Counter[tuple[str, str]] = Counter()
        self._lock = threading.Lock()

    def __call__(self, request: ModelRequest) -> Message:
        system = "".join(str(block.get("text", "")) for block in request.system)
        role = next((name for text, name in self.prompts.items() if system.startswith(text)), None)
        if role is None:
            raise LookupError("no scripted answers for this prompt")
        text = json.dumps(request.messages, default=str)
        # A key is a company's domain or name, or "domain|worker" for one research worker;
        # the company comes first in every request, so a later mention may be a source.
        present = [
            key for key in self.answers[role] if all(part in text for part in key.split("|"))
        ]
        present.sort(key=lambda key: (-key.count("|"), text.index(key.split("|")[0])))
        domain = present[0] if present else None
        if domain is None:
            raise LookupError(f"no scripted {role} answer for the company in this request")
        with self._lock:
            self.asked[(role, domain)] += 1
            index = self.asked[(role, domain)] - 1
        script = self.answers[role][domain]
        answer = script[min(index, len(script) - 1)]
        usage = {key: int(answer[key]) for key in USAGE_KEYS if key in answer}
        return fake_message(
            request.model,
            data=answer.get("data"),
            text=answer.get("text"),
            content=answer.get("content"),
            stop_reason=str(answer.get("stop_reason", "end_turn")),
            web_search_requests=int(answer.get("web_search_requests", 0)),
            **usage,
        )

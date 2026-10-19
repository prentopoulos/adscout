"""Prompt files, their versions, and requests with a stable cached prefix.

Each role's instructions live in `src/adscout/prompts/<role>.md`, its output schema beside it
in `<role>.schema.json`. A role's prompt version is `p-` and the first 12 hex digits of a
SHA-256 over the LF-normalized prompt and schema files (design decision 21); a lead carries
the prompt set's version, a digest over every role's version, from its creation.

Requests put the fixed text first and end it with a cache breakpoint, then the per-lead data,
serialized deterministically, so every lead of a run shares the cached prefix (decision 18).
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anthropic.types import CacheControlEphemeralParam, MessageParam, TextBlockParam

from adscout.llm.adapter import Effort, ModelRequest

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
EPHEMERAL: CacheControlEphemeralParam = {"type": "ephemeral"}


@dataclass(frozen=True)
class Prompt:
    role: str
    text: str
    schema: dict[str, Any] | None
    version: str


def lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def version_of(prompt: bytes, schema: bytes | None) -> str:
    digest = hashlib.sha256(lf(prompt) + b"\0" + lf(schema or b"")).hexdigest()
    return f"p-{digest[:12]}"


def load_prompt(role: str, folder: Path = PROMPT_DIR) -> Prompt:
    prompt_bytes = (folder / f"{role}.md").read_bytes()
    schema_path = folder / f"{role}.schema.json"
    schema_bytes = schema_path.read_bytes() if schema_path.exists() else None
    return Prompt(
        role=role,
        text=lf(prompt_bytes).decode("utf-8").strip(),
        schema=json.loads(schema_bytes) if schema_bytes is not None else None,
        version=version_of(prompt_bytes, schema_bytes),
    )


def roles(folder: Path = PROMPT_DIR) -> list[str]:
    return sorted(path.stem for path in folder.glob("*.md"))


def prompt_set_version(folder: Path = PROMPT_DIR) -> str:
    """One version for every prompt together: what a lead records at its creation."""
    lines = "".join(f"{role} {load_prompt(role, folder).version}\n" for role in roles(folder))
    return f"p-{hashlib.sha256(lines.encode('utf-8')).hexdigest()[:12]}"


def canonical_json(data: Any) -> str:
    """Sorted keys and fixed separators: the same data always gives the same bytes."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(", ", ": "))


def data_block(tag: str, data: Any) -> str:
    """Untrusted data wrapped in delimiters the prompts tell the model never to obey."""
    return f"<{tag}>\n{canonical_json(data)}\n</{tag}>"


def fixed_system(*parts: str) -> list[TextBlockParam]:
    """The fixed instructions as one system block ending in a cache breakpoint."""
    return [{"type": "text", "text": "\n\n".join(parts), "cache_control": EPHEMERAL}]


def request_for(
    prompt: Prompt,
    model: str,
    *,
    max_tokens: int,
    effort: Effort,
    fixed: tuple[str, ...] = (),
    user: str,
) -> ModelRequest:
    """A one-turn request: the prompt and fixed text cached, then this lead's content."""
    messages: list[MessageParam] = [{"role": "user", "content": user}]
    return ModelRequest(
        model=model,
        max_tokens=max_tokens,
        system=fixed_system(prompt.text, *fixed),
        messages=messages,
        output_schema=prompt.schema,
        effort=effort,
    )


def cached_prefix(request: ModelRequest) -> bytes:
    """The bytes up to the last cache breakpoint, in render order: tools, system, messages."""
    blocks: list[Any] = [*request.tool_specs(), *request.system]
    for message in request.messages:
        content = message["content"]
        blocks.extend(content if isinstance(content, list) else [content])
    last = max(
        (
            index
            for index, block in enumerate(blocks)
            if isinstance(block, dict) and "cache_control" in block
        ),
        default=-1,
    )
    return json.dumps(blocks[: last + 1], sort_keys=True, default=str).encode("utf-8")

"""Scripted model responses for the fake adapter mode (tests and the offline demo).

A fake response is an ordinary SDK `Message`, so code under test reads it exactly as it
reads a live one. Fake usage is what the script says, never a measurement.
"""

import itertools
import json
from collections.abc import Callable, Iterable
from typing import Any

from anthropic.types import Message

from adscout.llm.adapter import ModelRequest

_ids = itertools.count(1)


def fake_message(
    model: str,
    *,
    text: str | None = None,
    data: Any = None,
    content: list[dict[str, Any]] | None = None,
    stop_reason: str = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 20,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
    web_search_requests: int = 0,
) -> Message:
    """A response with text, JSON `data` as text, or explicit content blocks."""
    if content is None:
        body = text if text is not None else json.dumps(data, sort_keys=True)
        content = [{"type": "text", "text": body}]
    usage: dict[str, Any] = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_write_tokens,
        "cache_read_input_tokens": cache_read_tokens,
        "cache_creation": {
            "ephemeral_5m_input_tokens": cache_write_tokens,
            "ephemeral_1h_input_tokens": 0,
        },
    }
    if web_search_requests:
        usage["server_tool_use"] = {
            "web_search_requests": web_search_requests,
            "web_fetch_requests": 0,
        }
    return Message.model_validate(
        {
            "id": f"msg_fake_{next(_ids):06d}",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": usage,
        }
    )


def scripted(
    responses: Iterable[Message | Exception],
) -> Callable[[ModelRequest], Message]:
    """A responder that answers successive requests from a list, raising listed errors."""
    queue = list(responses)

    def respond(request: ModelRequest) -> Message:
        if not queue:
            raise AssertionError(f"no scripted response left for a {request.model} request")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return respond

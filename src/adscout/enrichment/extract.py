"""Model extraction of categories, markets, launches and a stated employee count from pages.

Haiku reads the company's pages (design decisions 8 and 14). Every value must name the page
that states it; a value citing a page that was not read is dropped. When a key field
extracted by Haiku fails its validator, the extraction is escalated once to Sonnet and the
Haiku values are kept as dropped, replaced by the escalation.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from adscout.config import SegmentConfig
from adscout.db.connection import utc_now
from adscout.enrichment.fields import Candidate, Checked, check
from adscout.enrichment.pages import text_of
from adscout.llm.adapter import CallContext, Effort, ModelAdapter, ModelResult
from adscout.llm.invoke import HAIKU, SONNET, InvalidOutput, escalate, invoke
from adscout.llm.prompts import Prompt, neutralize, request_for
from adscout.sources.fetcher import Page

PAGE_CHARS = 12_000  # about 4K tokens per page at 3 bytes a token
MAX_TOKENS = 1_500
EFFORT: Effort = "low"
ESCALATE_ON = ("categories", "sells_in")


@dataclass(frozen=True)
class Extraction:
    rows: list[Checked]
    escalated: bool
    call_ids: list[str]


def page_blocks(pages: Sequence[Page]) -> str:
    return "\n\n".join(
        f'<page url="{page.final_url}">\n{neutralize(text_of(page.text)[:PAGE_CHARS], "page")}'
        "\n</page>"
        for page in pages
    )


def extraction_request(
    prompt: Prompt, segment: SegmentConfig, name: str, pages: Sequence[Page], model: str
) -> Any:
    categories = "Segment categories (use these IDs only): " + ", ".join(segment.categories)
    company = f"Company: {neutralize(name, 'page')}"
    return request_for(
        prompt,
        model,
        max_tokens=MAX_TOKENS,
        effort=EFFORT,
        fixed=(categories,),
        user=f"{company}\n\n{page_blocks(pages)}",
    )


def candidates(data: Any, result: ModelResult, pages: Sequence[Page]) -> list[Candidate]:
    """The extraction's values as candidates; a value citing an unread page is dropped later."""
    if not isinstance(data, dict):
        raise InvalidOutput("the answer is not a JSON object")
    now = utc_now()
    by_url = {page.final_url: page for page in pages}

    def candidate(field: Any, value: Any, url: Any, as_of: str | None = None) -> Candidate:
        page = by_url.get(str(url))
        return Candidate(
            field=field,
            value=value,
            source_url=str(url) if page else f"unread:{url}",
            source_kind="company_site",
            method="extracted",
            retrieved_at=now,
            as_of=as_of,
            source_call_id=page.call_id if page else None,
            model_call_id=result.call_id,
        )

    found = []
    for field in ("categories", "sells_in"):
        part = data.get(field) or {}
        if part.get("values"):
            found.append(candidate(field, part["values"], part.get("source_url")))
    launches = data.get("recent_launches") or []
    by_page: dict[str, list[dict[str, Any]]] = {}
    for launch in launches:
        by_page.setdefault(str(launch.get("source_url")), []).append(launch)
    for url, items in by_page.items():
        found.append(candidate("recent_launches", items, url))
    employees = data.get("employee_count")
    if isinstance(employees, dict):
        found.append(
            candidate(
                "employee_count",
                employees.get("count"),
                employees.get("source_url"),
                str(employees.get("year") or "") or None,
            )
        )
    return found


def parse(result: ModelResult) -> Any:
    try:
        data = result.json()
    except ValueError as error:
        raise InvalidOutput(f"the answer is not JSON: {error}") from None
    if not isinstance(data, dict) or not {"categories", "sells_in"} <= set(data):
        raise InvalidOutput("the answer misses the categories or sells_in object")
    return data


def extract(
    adapter: ModelAdapter,
    prompt: Prompt,
    segment: SegmentConfig,
    name: str,
    pages: Sequence[Page],
    context: CallContext,
    today: date,
    model: str = HAIKU,
) -> Extraction:
    request = extraction_request(prompt, segment, name, pages, model)
    first = invoke(adapter, request, context, parse)
    rows = _checked(candidates(first.value, first.result, pages), segment, today)
    if model != HAIKU or first.call_role == "fallback" or not _key_field_failed(rows):
        return Extraction(rows, False, [first.result.call_id])
    second = escalate(adapter, request, context, parse, SONNET)
    replaced = [
        replace(row, status="dropped", detail="replaced by the escalation to Sonnet")
        if row.status == "valid"
        else row
        for row in rows
    ]
    rows = replaced + _checked(candidates(second.value, second.result, pages), segment, today)
    return Extraction(rows, True, [first.result.call_id, second.result.call_id])


def _checked(found: list[Candidate], segment: SegmentConfig, today: date) -> list[Checked]:
    rows: list[Checked] = []
    for item in found:
        if item.source_url.startswith("unread:"):
            url = item.source_url.removeprefix("unread:")
            rows.append(
                Checked(
                    item, item.value, "dropped", f"cites {url}, which is not a page that was read"
                )
            )
        else:
            rows.extend(check(item, segment.categories, today))
    return rows


def _key_field_failed(rows: Sequence[Checked]) -> bool:
    return any(row.field in ESCALATE_ON and row.status == "dropped" for row in rows)

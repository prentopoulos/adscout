"""The claim verifier: code, not a model, decides which research claims are kept (decision 27).

A claim is kept only if its URL equals, after normalization, a URL fetched successfully in
this run; its quote of at least 20 characters appears in that page's text after NFKC,
quote-mark, whitespace and case normalization; and every number in the claim appears in the
quote. A claim that names a person by role ("CEO", "founder", "said") is dropped too, since
AdScout never stores a real person's name (PROJECT.md §5); that test is a conservative
heuristic, so it may drop some company claims. Dropped claims are kept, counted and stored
with their reasons, never shown to the merge or the writer.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from adscout.research.handoffs import Claim, VerifiedClaim

VERIFIER_VERSION = "v1"
MIN_QUOTE = 20
PREFIX = {
    "worker_audience": "A",
    "worker_ads": "D",
    "worker_launches": "L",
    "research_single": "S",
}
# A number not glued to a preceding letter: "K1" is a name, "2M" and "RTX 4090" have numbers.
NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*")
# Curly quotes and dashes (by code point) read as their plain forms.
QUOTES = str.maketrans(
    {
        chr(0x2018): "'",
        chr(0x2019): "'",
        chr(0x201C): '"',
        chr(0x201D): '"',
        chr(0x2013): "-",
        chr(0x2014): "-",
    }
)
ROLE = re.compile(
    r"\b(ceo|cfo|coo|cto|cmo|chief \w+ officer|founder|co-founder|president|chairman|"
    r"chairwoman|chairperson|spokesperson|spokesman|spokeswoman|vice president|vp|director|"
    r"head of|manager|executive|said|says|told|according to)\b",
    re.IGNORECASE,
)
CAPITALIZED_PAIR = re.compile(
    r"\b([A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?)\s+([A-Z][a-z]+(?:[-'][A-Z]?[a-z]+)?)\b"
)


@dataclass(frozen=True)
class FetchedPage:
    """A page fetched successfully in this run: its text and its `source_calls` row."""

    url: str
    text: str
    call_id: str


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).translate(QUOTES).casefold().split())


def numbers(text: str) -> set[str]:
    """Numbers as written, thousands separators removed: "1,500" and "1500" are equal."""
    found = set()
    for match in NUMBER.findall(text):
        value = (
            match.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", match) else match
        )
        found.add(value.rstrip("0").rstrip(".") if "." in value else value)
    return found


def names_individual(claim: Claim, company: str) -> bool:
    """A role word and a capitalized name-like pair that is not the company's name."""
    company_words = {word.lower() for word in re.findall(r"[A-Za-z]+", company)}
    for text in (claim.text, claim.quote):
        if not ROLE.search(text):
            continue
        for first, last in CAPITALIZED_PAIR.findall(text):
            if first.lower() not in company_words and last.lower() not in company_words:
                return True
    return False


def verify(
    worker: str,
    claims: Iterable[Claim],
    fetched: dict[str, FetchedPage],
    company: str,
    start: int = 1,
) -> list[VerifiedClaim]:
    """Check each claim against the pages this run fetched; `fetched` is by normalized URL."""
    prefix = PREFIX.get(worker, "C")
    checked = []
    for number, claim in enumerate(claims, start=start):
        page = fetched.get(normalize_url(claim.source_url))
        quote = normalize_text(claim.quote)
        quote_found = (
            bool(page)
            and len(quote) >= MIN_QUOTE
            and quote in normalize_text(page.text if page else "")
        )
        checked.append(
            VerifiedClaim(
                claim_id=f"{prefix}{number}",
                worker=worker,
                claim=claim,
                fetch_call_id=page.call_id if page else None,
                url_fetched_in_run=page is not None,
                quote_found=quote_found,
                numbers_ok=numbers(claim.text) <= numbers(claim.quote),
                names_individual=names_individual(claim, company),
                verifier_version=VERIFIER_VERSION,
            )
        )
    return checked


def drop_reason(claim: VerifiedClaim) -> str | None:
    if not claim.url_fetched_in_run:
        return "its URL was not fetched in this run"
    if not claim.quote_found:
        return "its quote is not on the page (or is under 20 characters)"
    if not claim.numbers_ok:
        return "it has a number its quote does not"
    if claim.names_individual:
        return "it names a person"
    return None

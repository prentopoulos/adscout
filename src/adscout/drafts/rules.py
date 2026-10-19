"""The deterministic draft rule checker (design decision 31). Code, not a model, decides.

A draft is a subject and structured sentences, each naming its supports: this lead's
verified claim IDs or media-kit fact IDs. The checker fails a draft when a sentence that
states something checkable (a digit, a proper noun, a date, a URL or a superlative) has no
valid support; when a sentence's numbers are not among its supports' numbers; when a proper
noun is in none of its supports, the company's name, the publisher's name or the allowlist;
when the subject passes 70 characters or the body falls outside 60 to 160 words; when a
footer placeholder is missing or repeated; when it holds an email address, phone number,
person's name or URL; when it uses a banned phrase; when the company's name is not written
exactly; or when it repeats injection canary text. The footer is code's, not the writer's.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from adscout.config import contact_kind
from adscout.research.verifier import ROLE, numbers

SUBJECT_MAX = 70
BODY_WORDS = (60, 160)
PLACEHOLDERS = (
    "{{sender_name}}",
    "{{sender_title}}",
    "{{publisher_postal_address}}",
    "{{unsubscribe_url}}",
)
BANNED = (
    "guarantee",
    "act now",
    "limited time",
    "don't miss",
    "last chance",
    "urgent",
    "risk-free",
    "our partnership",
    "in partnership with",
    "partnered with",
    "official partner",
    "endorsed by",
    "affiliated with",
    "as you know",
)
SUPERLATIVE = re.compile(
    r"\b(best|biggest|largest|greatest|leading|top|most|fastest|first|only|unmatched|"
    r"unrivaled|number one)\b|#1",
    re.IGNORECASE,
)
MONTH = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|"
    r"december)\b",
    re.IGNORECASE,
)
URL = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(com|net|org|io|gg|tv|co)\b", re.IGNORECASE)
CAPITALIZED = re.compile(r"\b[A-Z][A-Za-z0-9&'.-]*")
CANARY = re.compile(r"ADSCOUT-CANARY-[A-Z0-9-]+")
PERSON = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")


@dataclass(frozen=True)
class Sentence:
    text: str
    supports: list[str]


@dataclass(frozen=True)
class Draft:
    subject: str
    sentences: list[Sentence]

    @property
    def message(self) -> str:
        return " ".join(sentence.text.strip() for sentence in self.sentences)


@dataclass(frozen=True)
class Problem:
    rule: str
    detail: str
    sentence: int | None = None

    def __str__(self) -> str:
        where = f"sentence {self.sentence + 1}: " if self.sentence is not None else ""
        return f"{self.rule}: {where}{self.detail}"


def footer(publisher: str) -> str:
    """The sign-off the Phase 3 send function fills; it refuses a message without it."""
    return (
        "{{sender_name}}\n{{sender_title}}, " + publisher + "\n{{publisher_postal_address}}\n"
        "Unsubscribe: {{unsubscribe_url}}"
    )


def body(draft: Draft, publisher: str) -> str:
    return f"{draft.message}\n\n{footer(publisher)}"


def words(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9&'-]+", text)}


def check(
    draft: Draft,
    *,
    company: str,
    publisher: str,
    claims: dict[str, str],
    facts: dict[str, str],
    allowlist: Iterable[str] = (),
    canaries: Sequence[str] = (),
) -> list[Problem]:
    """Every rule the draft breaks; an empty list is a pass."""
    problems: list[Problem] = []
    supports_known = {**claims, **facts}
    names = (
        words(company)
        | words(publisher)
        | {word.lower() for item in allowlist for word in re.findall(r"[A-Za-z0-9&'-]+", item)}
    )
    if not draft.subject.strip() or len(draft.subject) > SUBJECT_MAX:
        problems.append(
            Problem("subject_length", f"{len(draft.subject)} characters; 1 to {SUBJECT_MAX}")
        )
    count = len(draft.message.split())
    low, high = BODY_WORDS
    if not low <= count <= high:
        problems.append(Problem("body_length", f"{count} words; {low} to {high}"))
    full = body(draft, publisher)
    for placeholder in PLACEHOLDERS:
        found = full.count(placeholder)
        if found != 1:
            problems.append(Problem("footer", f"{placeholder} appears {found} times; exactly once"))
    for index, sentence in enumerate(draft.sentences):
        own = words(company) | words(publisher)
        problems.extend(_sentence(index, sentence, supports_known, names, own, canaries))
    everything = f"{draft.subject} {draft.message}"
    if company not in everything:
        problems.append(Problem("company_name", f"{company!r} is not written exactly"))
    for match in re.finditer(re.escape(company), everything, re.IGNORECASE):
        if match.group(0) != company:
            problems.append(Problem("company_name", f"{match.group(0)!r} should read {company!r}"))
    if any(placeholder in everything for placeholder in PLACEHOLDERS) or "{{" in everything:
        problems.append(Problem("footer", "placeholders belong to the footer only"))
    return problems


def _sentence(
    index: int,
    sentence: Sentence,
    supports_known: dict[str, str],
    names: set[str],
    own: set[str],
    canaries: Sequence[str],
) -> list[Problem]:
    text = sentence.text
    problems: list[Problem] = []
    unknown = [support for support in sentence.supports if support not in supports_known]
    if unknown:
        problems.append(
            Problem(
                "unknown_support",
                f"supports {unknown} are not this lead's claims or media-kit facts",
                index,
            )
        )
    support_text = " ".join(supports_known[s] for s in sentence.supports if s in supports_known)
    tokens = CAPITALIZED.findall(text)[1:]  # the first word of a sentence is capitalized anyway
    proper = [name for name in (_bare(token) for token in tokens) if name]
    # Naming the company or the publisher states nothing that needs a source.
    named = [name for name in proper if not words(name) <= own]
    checkable = bool(
        re.search(r"\d", text)
        or named
        or MONTH.search(text)
        or URL.search(text)
        or SUPERLATIVE.search(text)
    )
    if checkable and not support_text:
        problems.append(
            Problem("unsupported", "states a checkable fact with no valid support", index)
        )
    stray = sorted(numbers(text) - numbers(support_text))
    if support_text and stray:
        problems.append(Problem("numbers", f"numbers {stray} are not in its supports", index))
    allowed = names | words(support_text)
    unsupported_names = sorted(
        {token for token in proper if token.lower() not in allowed and not words(token) <= allowed}
    )
    if unsupported_names:
        problems.append(
            Problem(
                "proper_nouns", f"{unsupported_names} are in no support, name or allowlist", index
            )
        )
    kind = contact_kind(text)
    if kind:
        problems.append(Problem("contact_data", f"contains {kind}", index))
    if URL.search(text):
        problems.append(Problem("url", "a draft carries no URL", index))
    if ROLE.search(text) and PERSON.search(text):
        problems.append(Problem("person", "names a person", index))
    lowered = text.lower()
    banned = [phrase for phrase in BANNED if phrase in lowered]
    if banned:
        problems.append(Problem("banned_phrase", f"uses {banned}", index))
    if CANARY.search(text) or any(canary and canary in text for canary in canaries):
        problems.append(Problem("canary", "repeats injection canary text", index))
    return problems


def _bare(token: str) -> str:
    """A capitalized token without trailing punctuation or a possessive "'s"."""
    token = token.strip(".'").replace(chr(0x2019), "'")  # a curly apostrophe
    return token.removesuffix("'s").strip(".'")

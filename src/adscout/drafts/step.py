"""The real `draft` step: writer, rule checker, critic, at most two rewrites (decision 30).

The writer (Sonnet, no tools) writes a subject and structured sentences citing this lead's
verified claims and the media kit's facts. The deterministic rule checker runs first; only a
draft that passes it goes to the critic (Sonnet, no tools), so the critic can never pass a
draft the rules fail. Rule problems or critic issues go back to the writer, at most twice.
Rules still failing after that exit as `draft_failed` for a person; rules passing with the
critic still objecting give `pending_approval` flagged `critic_unresolved`, its notes kept.
Every draft stops at approval: nothing here sends anything.
"""

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field, replace
from typing import Any

from adscout.db.connection import utc_now
from adscout.drafts.media_kit import MediaKit
from adscout.drafts.rules import Draft, Problem, Sentence, body, check
from adscout.llm.adapter import CallContext, ModelAdapter, ModelCallFailed, ModelResult
from adscout.llm.invoke import CallsFailed, InvalidOutput, invoke
from adscout.llm.prompts import Prompt, data_block, request_for
from adscout.pipeline.contracts import Lead, Outcome
from adscout.pipeline.registry import node
from adscout.research.handoffs import SummaryPoint, VerifiedClaim
from adscout.spans import Span, step_span

MAX_REWRITES = 2
WRITER_TOKENS = 1_500
CRITIC_TOKENS = 800
REVISE = "Revise the draft to fix these problems, keeping what works:\n{problems}"


@dataclass(frozen=True)
class Critique:
    verdict: str
    issues: list[dict[str, str]]


@dataclass
class Attempt:
    number: int
    draft: Draft | None = None
    problems: list[Problem] = field(default_factory=list)
    critique: Critique | None = None
    note: str | None = None


@dataclass(frozen=True)
class Drafted:
    lead: Lead
    attempts: list[Attempt]
    outcome: Outcome
    publisher_id: str
    publisher_name: str

    @property
    def final(self) -> Attempt:
        return self.attempts[-1]


def kit_text(kit: MediaKit) -> str:
    facts = "\n".join(f"- {fact.id}: {fact.text}" for fact in kit.facts)
    return f"## Publisher: {kit.name} (fictional)\nMedia-kit facts:\n{facts}"


@dataclass
class Drafter:
    adapter: ModelAdapter
    kit: MediaKit
    writer_prompt: Prompt
    critic_prompt: Prompt
    canaries: tuple[str, ...] = ()

    def draft(
        self,
        lead: Lead,
        points: list[SummaryPoint],
        claims: list[VerifiedClaim],
        run_id: str,
    ) -> Drafted:
        span = step_span(run_id, lead.lead_id, "draft")
        writer_node = node("writer")
        cap = (writer_node.caps.cost_usd if writer_node.caps else {}).get(writer_node.model or "")
        brief = {
            "company": lead.name,
            "summary_points": [point.model_dump() for point in points],
            "claims": [{"id": claim.claim_id, "text": claim.claim.text} for claim in claims],
        }
        request = request_for(
            self.writer_prompt,
            writer_node.model or "",
            max_tokens=WRITER_TOKENS,
            effort=writer_node.effort or "medium",
            fixed=(kit_text(self.kit),),
            user=data_block("brief", brief),
        )
        known_claims = {claim.claim_id: claim.claim.text for claim in claims}
        attempts: list[Attempt] = []
        for number in range(1, MAX_REWRITES + 2):
            attempt = Attempt(number)
            attempts.append(attempt)
            # Every draft call for this lead so far, retries and fallbacks included.
            spent = self.adapter.sink.spent(lead.lead_id, "draft")
            if cap is not None and spent >= cap:
                attempt.note = f"draft cost cap ${cap} reached"
                break
            writer_span = span.child("writer")
            try:
                written = invoke(
                    self.adapter,
                    request,
                    self._context(run_id, lead, "writer", writer_span),
                    parse_draft,
                )
            except (CallsFailed, ModelCallFailed) as error:
                attempt.note = f"writer failed: {error}"
                self.adapter.sink.add(writer_span.close("failed", "writer failed"))
                break
            self.adapter.sink.add(writer_span.close("succeeded", f"attempt {number}"))
            attempt.draft = written.value
            attempt.problems = check(
                written.value,
                company=lead.name,
                publisher=self.kit.name,
                claims=known_claims,
                facts={fact.id: fact.text for fact in self.kit.facts},
                allowlist=self.kit.allowlist,
                canaries=self.canaries,
            )
            feedback = [str(problem) for problem in attempt.problems]
            if not attempt.problems:
                attempt.critique = self._critique(lead, written.value, brief, run_id, span)
                if attempt.critique.verdict == "approve":
                    break
                feedback = [f"{i['aspect']}: {i['problem']}" for i in attempt.critique.issues]
            if number <= MAX_REWRITES:
                request = _revised(request, written.result, feedback)
        outcome = _outcome(lead, attempts)
        self.adapter.sink.add(span.close("succeeded", outcome.detail))
        return Drafted(lead, attempts, outcome, self.kit.publisher_id, self.kit.name)

    def _critique(
        self, lead: Lead, draft: Draft, brief: dict[str, Any], run_id: str, span: Span
    ) -> Critique:
        critic_node = node("critic")
        critic_span = span.child("critic")
        shown = {"subject": draft.subject, "message": draft.message}
        request = request_for(
            self.critic_prompt,
            critic_node.model or "",
            max_tokens=CRITIC_TOKENS,
            effort=critic_node.effort or "low",
            user=f"{data_block('draft', shown)}\n\n{data_block('brief', brief)}",
        )
        try:
            critique = invoke(
                self.adapter,
                request,
                self._context(run_id, lead, "critic", critic_span),
                parse_critique,
            ).value
        except (CallsFailed, ModelCallFailed) as error:
            critique = Critique(
                "revise", [{"aspect": "review", "problem": f"critic failed: {error}"}]
            )
        self.adapter.sink.add(critic_span.close("succeeded", critique.verdict))
        return critique

    def _context(self, run_id: str, lead: Lead, agent: str, span: Span) -> CallContext:
        prompt = self.writer_prompt if agent == "writer" else self.critic_prompt
        return CallContext(
            run_id=run_id,
            step="draft",
            lead_id=lead.lead_id,
            role=agent,
            agent_name=agent,
            prompt_version=prompt.version,
            parent_span_id=span.span_id,
            allowed_tools=node(agent).tools,
        )


def parse_draft(result: ModelResult) -> Draft:
    try:
        data = result.json()
    except ValueError as error:
        raise InvalidOutput(f"the draft is not JSON: {error}") from None
    if not isinstance(data, dict) or not isinstance(data.get("sentences"), list):
        raise InvalidOutput("the draft has no sentences list")
    sentences = []
    for item in data["sentences"]:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            raise InvalidOutput("a sentence is malformed")
        supports = item.get("supports") or []
        if not isinstance(supports, list) or not all(isinstance(s, str) for s in supports):
            raise InvalidOutput("a sentence's supports are not a list of IDs")
        sentences.append(Sentence(item["text"], list(supports)))
    return Draft(str(data.get("subject") or ""), sentences)


def parse_critique(result: ModelResult) -> Critique:
    try:
        data = result.json()
    except ValueError as error:
        raise InvalidOutput(f"the critique is not JSON: {error}") from None
    verdict = data.get("verdict") if isinstance(data, dict) else None
    issues = data.get("issues") if isinstance(data, dict) else None
    if verdict not in ("approve", "revise") or not isinstance(issues, list):
        raise InvalidOutput("the critique needs a verdict and an issues list")
    if verdict == "revise" and not issues:
        raise InvalidOutput("a revise verdict needs at least one issue")
    return Critique(str(verdict), [dict(issue) for issue in issues if isinstance(issue, dict)])


def _revised(request: Any, result: ModelResult, feedback: list[str]) -> Any:
    messages = [
        *request.messages,
        {"role": "assistant", "content": result.text or "(empty)"},
        {"role": "user", "content": REVISE.format(problems="\n".join(f"- {f}" for f in feedback))},
    ]
    return replace(request, messages=messages)


def _outcome(lead: Lead, attempts: list[Attempt]) -> Outcome:
    final = attempts[-1]
    passing = final.draft is not None and not final.problems
    if not passing:
        why = final.note or "; ".join(str(problem) for problem in final.problems)
        return Outcome(
            lead_id=lead.lead_id,
            outcome="exited",
            reason="draft_failed",
            detail=f"draft failed after {len(attempts)} attempts: {why}; for a person",
        )
    critique = final.critique
    if critique is not None and critique.verdict == "approve":
        return Outcome(lead_id=lead.lead_id, outcome="kept", detail="pending_approval")
    return Outcome(
        lead_id=lead.lead_id,
        outcome="kept",
        flag="critic_unresolved",
        detail="pending_approval; the critic still objects: "
        + "; ".join(
            f"{i['aspect']}: {i['problem']}" for i in (critique.issues if critique else [])
        ),
    )


def store(
    connection: sqlite3.Connection, run_id: str, drafted: Drafted, brief_id: int | None
) -> None:
    """One `drafts` row: the last attempt, with every attempt's checks and critic notes."""
    final = drafted.final
    draft = final.draft or next((a.draft for a in reversed(drafted.attempts) if a.draft), None)
    text = body(draft, drafted.publisher_name) if draft else ""
    status = "pending_approval" if drafted.outcome.outcome == "kept" else "failed_checks"
    connection.execute(
        "INSERT INTO drafts (lead_id, run_id, implementation, revision, subject, body, "
        "body_sha256, status, created_at, sentences_json, checks_json, critic_notes_json, "
        "publisher_id, brief_id) VALUES (?, ?, 'real', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            drafted.lead.lead_id,
            run_id,
            len(drafted.attempts),
            draft.subject if draft else "",
            text,
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
            status,
            utc_now(),
            json.dumps(
                [
                    {"text": s.text, "supports": s.supports}
                    for s in (draft.sentences if draft else [])
                ]
            ),
            json.dumps(
                [
                    {"attempt": a.number, "problems": [str(p) for p in a.problems], "note": a.note}
                    for a in drafted.attempts
                ]
            ),
            json.dumps(
                [
                    {
                        "attempt": a.number,
                        "verdict": a.critique.verdict,
                        "issues": a.critique.issues,
                    }
                    for a in drafted.attempts
                    if a.critique
                ]
            ),
            drafted.publisher_id,
            brief_id,
        ),
    )

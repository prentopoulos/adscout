"""The one CRM writer (PROJECT.md §5). No other module writes CRM tables.

It deduplicates accounts by company domain, writes only AdScout-owned fields, never
overwrites a field a person edited, and logs every write. In Phase 1 its target is the local
fake CRM (`fake_crm_*` tables); Phase 4 adds the real sandbox behind the same functions.
"""

import json
import sqlite3
from dataclasses import dataclass
from typing import Literal

from adscout.db.connection import utc_now
from adscout.ids import uuid7

TARGET = "local_fake"
# The fields AdScout owns on a CRM account. Anything else belongs to people.
OWNED_FIELDS = frozenset(
    {
        "name",
        "adscout_lead_id",
        "adscout_segment",
        "adscout_source",
        "adscout_agent_version",
        "adscout_prompt_version",
        "adscout_score",
        "adscout_brief_summary",
        "adscout_draft_subject",
        "adscout_approval_id",
        "adscout_approver_kind",
    }
)


class CrmWriteRefused(ValueError):
    """The writer was asked to write a field AdScout does not own."""


@dataclass(frozen=True)
class WriteResult:
    operation_id: str
    operation: Literal["create", "update", "no_op"]
    written: tuple[str, ...]
    skipped: tuple[str, ...]


def account_exists(connection: sqlite3.Connection, domain: str) -> bool:
    row = connection.execute("SELECT 1 FROM fake_crm_accounts WHERE domain = ?", (domain,))
    return row.fetchone() is not None


def write_account(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    lead_id: str,
    approval_id: str,
    domain: str,
    fields: dict[str, str | None],
) -> WriteResult:
    """Create or update the account for `domain`, inside the caller's transaction."""
    foreign = sorted(set(fields) - OWNED_FIELDS)
    if foreign:
        raise CrmWriteRefused(f"not AdScout-owned fields: {', '.join(foreign)}")
    now = utc_now()
    row = connection.execute(
        "SELECT crm_account_id FROM fake_crm_accounts WHERE domain = ?", (domain,)
    ).fetchone()
    created = row is None
    if created:
        cursor = connection.execute(
            "INSERT INTO fake_crm_accounts (domain, created_by, created_at) "
            "VALUES (?, 'adscout', ?)",
            (domain, now),
        )
        account_id = int(cursor.lastrowid or 0)
    else:
        account_id = int(row["crm_account_id"])
    current = {
        item["field"]: item
        for item in connection.execute(
            "SELECT field, value, owner FROM fake_crm_account_fields WHERE crm_account_id = ?",
            (account_id,),
        ).fetchall()
    }
    written, skipped = [], []
    for name, value in sorted(fields.items()):
        existing = current.get(name)
        if existing is not None and existing["value"] == value:
            continue
        if existing is not None and existing["owner"] == "person":
            skipped.append(name)  # a person edited it; theirs stands
            continue
        connection.execute(
            "INSERT INTO fake_crm_account_fields (crm_account_id, field, value, owner, "
            "updated_at) VALUES (?, ?, ?, 'adscout', ?) "
            "ON CONFLICT (crm_account_id, field) DO UPDATE SET value = excluded.value, "
            "owner = 'adscout', updated_at = excluded.updated_at",
            (account_id, name, value, now),
        )
        written.append(name)
    operation: Literal["create", "update", "no_op"] = (
        "create" if created else "update" if written else "no_op"
    )
    result = WriteResult(str(uuid7()), operation, tuple(written), tuple(skipped))
    detail = f"{operation} on {TARGET}"
    if skipped:
        detail += f"; kept the person's value of {', '.join(skipped)}"
    connection.execute(
        "INSERT INTO crm_writes (operation_id, run_id, lead_id, approval_id, target, domain, "
        "operation, fields_written_json, fields_skipped_json, status, detail, written_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'applied', ?, ?)",
        (
            result.operation_id,
            run_id,
            lead_id,
            approval_id,
            TARGET,
            domain,
            operation,
            json.dumps(written),
            json.dumps(skipped),
            detail,
            now,
        ),
    )
    return result

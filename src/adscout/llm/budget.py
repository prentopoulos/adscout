"""Per-run spend caps: a worst-case reservation before each call, settled after it.

Workers run in parallel, so reservations are taken under a lock: a call proceeds only if the
run's settled spend plus every open reservation plus its own worst case stays within the cap
(Phase 2 design, decision 16). A refused reservation ends the run as `budget_exhausted`
(decision 17). Replays cost nothing and reserve nothing.

The worst case of a call is its `max_tokens` output, its whole prompt priced as uncached
input, and `max_uses` searches with their fees. The prompt's token count is not known before
the call, so it is estimated from the request's UTF-8 size, plus the tool-use system prompt
and an allowance for the results each search adds. Settling corrects every reservation to
the call's actual cost, so a low estimate can let the run overshoot its cap by at most the
error on the calls in flight; the workspace spend limit is the backstop.
"""

import math
import threading
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from adscout.llm.prices import PriceTable, Usage, cost

# Estimate inputs (checked against measured usage in the first live run, task 10.2).
BYTES_PER_TOKEN = 3  # English prose runs nearer 4 bytes per token; JSON and URLs fewer
TOOL_SYSTEM_TOKENS = 286  # Haiku 5.5 and Sonnet 5.5 with tool_choice auto (pricing page)
SEARCH_RESULT_TOKENS = 3_000  # allowance for the result blocks one web search adds


class BudgetExhausted(RuntimeError):
    """The run's spend cap or the provider's spend limit stops further calls."""

    category = "budget_exhausted"


def estimate_prompt_tokens(request_bytes: int, has_tools: bool, max_searches: int) -> int:
    return (
        math.ceil(request_bytes / BYTES_PER_TOKEN)
        + (TOOL_SYSTEM_TOKENS if has_tools else 0)
        + SEARCH_RESULT_TOKENS * max_searches
    )


def worst_case_cost(
    table: PriceTable,
    model: str,
    *,
    prompt_tokens: int,
    max_tokens: int,
    max_searches: int,
    on: date,
) -> Decimal:
    """Uncached input, the full `max_tokens` output and every allowed search."""
    usage = Usage(
        input_tokens=prompt_tokens, output_tokens=max_tokens, web_search_requests=max_searches
    )
    return cost(table, model, usage, on).total_usd


@dataclass
class Reservation:
    amount: Decimal
    open: bool = True


class SpendLedger:
    """One run's spend: settled cost plus open reservations, never above the cap."""

    def __init__(self, cap_usd: Decimal | None) -> None:
        if cap_usd is not None and cap_usd <= 0:
            raise ValueError("a spend cap must be positive")
        self.cap_usd = cap_usd
        self.spent_usd = Decimal(0)
        self.reserved_usd = Decimal(0)
        self._lock = threading.Lock()

    def reserve(self, amount: Decimal) -> Reservation:
        """Hold `amount` for one call, or refuse if the cap would be passed."""
        with self._lock:
            committed = self.spent_usd + self.reserved_usd
            if self.cap_usd is not None and committed + amount > self.cap_usd:
                raise BudgetExhausted(
                    f"spend cap ${self.cap_usd} reached: ${self.spent_usd} spent, "
                    f"${self.reserved_usd} reserved, this call needs up to ${amount}"
                )
            self.reserved_usd += amount
            return Reservation(amount)

    def settle(self, reservation: Reservation, actual: Decimal) -> None:
        """Release the reservation and record what the call actually cost."""
        with self._lock:
            if not reservation.open:
                raise ValueError("this reservation was already settled")
            reservation.open = False
            self.reserved_usd -= reservation.amount
            self.spent_usd += actual

"""Which model transport a run uses: scripted fakes, a replay of a recorded run, or live.

Offline is the default (PROJECT.md §6): a run without `--live` makes no network call; its
model calls come from scripted answers or from the replay cache. Live mode needs the
`--live` flag, a spend cap and the API key (design decisions 13 and 16).
"""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from adscout.llm.adapter import (
    FakeTransport,
    ModelAdapter,
    ResponseRecorder,
    Transport,
    live_transport,
    require_live_settings,
)
from adscout.llm.budget import SpendLedger
from adscout.llm.cache import DEFAULT_CACHE, Recorder, ReplayCache, ReplayTransport
from adscout.llm.prices import PRICE_TABLE, load_price_table
from adscout.llm.scripted import ScriptedModels
from adscout.pipeline.recorder import Run, RunSource, Snapshot

ModelMode = Literal["fake", "replay", "live"]
SOURCES: dict[ModelMode, RunSource] = {"fake": "fixture", "replay": "replay", "live": "live"}


class ModelsNotChosen(ValueError):
    """An offline run needs scripted answers or a run to replay."""


@dataclass(frozen=True)
class ModelChoice:
    live: bool = False
    cap_usd: Decimal | None = None
    replay_run_id: str | None = None
    scripted: Path | None = None
    cache_path: Path = DEFAULT_CACHE

    @property
    def mode(self) -> ModelMode:
        if self.live:
            return "live"
        return "replay" if self.replay_run_id else "fake"

    @property
    def source(self) -> RunSource:
        return SOURCES[self.mode]

    def check(self) -> None:
        """Refuse an unusable choice before any run row is written."""
        if self.live and self.replay_run_id:
            raise ModelsNotChosen("choose --live or --replay, not both")
        if self.live:
            require_live_settings(live_flag=True, cap_usd=self.cap_usd)
        elif not self.replay_run_id and self.scripted is None:
            raise ModelsNotChosen(
                "an offline run needs scripted answers (--fixture-models) or a run to replay "
                "(--replay); live model calls need --live and --max-spend-usd"
            )


def price_snapshot() -> Snapshot:
    table = load_price_table(PRICE_TABLE)
    return Snapshot("price_table", table.content_hash(), table.model_dump(mode="json"))


def build_adapter(choice: ModelChoice, run: Run) -> tuple[ModelAdapter, ReplayCache | None]:
    """The adapter for a run; its call records go to the run's sink. Call after `check`."""
    cache: ReplayCache | None = None
    recorder: ResponseRecorder | None = None
    transport: Transport
    if choice.mode == "live":
        transport = live_transport()
        cache = ReplayCache(choice.cache_path)
        recorder = Recorder(cache, run.run_id)
    elif choice.replay_run_id is not None:
        cache = ReplayCache(choice.cache_path)
        transport = ReplayTransport(cache, choice.replay_run_id)
    elif choice.scripted is not None:
        transport = FakeTransport(ScriptedModels(choice.scripted))
    else:
        raise ModelsNotChosen("no scripted answers, replay run or live mode chosen")
    adapter = ModelAdapter(
        transport,
        load_price_table(PRICE_TABLE),
        SpendLedger(choice.cap_usd),
        run.calls,
        recorder=recorder,
    )
    return adapter, cache

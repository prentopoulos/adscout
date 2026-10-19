"""The fictional publisher's media kit: the only facts a draft may state about the sender.

`config/media-kit/<publisher_id>.yaml` holds a fictional publisher the owner names after
the agent checks the name is not a real company (design decision 32). Every fact has an ID,
text and `simulated: true`; loading fails when one does not. The allowlist holds proper
nouns a draft may use beyond its supports, the company's name and the publisher's name.
"""

from datetime import date
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from adscout.config import (
    SLUG,
    ConfigError,
    canonical_hash,
    error_text,
    load_yaml,
    reject_contact_data,
)
from adscout.ids import ROOT

MEDIA_KITS = ROOT / "config" / "media-kit"


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str = Field(pattern=r"^mk-[a-z0-9-]+$")
    text: str = Field(min_length=1, max_length=300)
    simulated: Literal[True]


class NameCheck(BaseModel):
    """How the publisher's name was checked not to be a real company."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    checked_on: date
    method: str = Field(min_length=1)
    result: str = Field(min_length=1)


class MediaKit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1"]
    publisher_id: str = Field(pattern=SLUG)
    name: str = Field(min_length=1, max_length=80)
    fictional: Literal[True]
    name_check: NameCheck
    facts: list[Fact] = Field(min_length=1)
    allowlist: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def label_facts(cls, data: object) -> object:
        """Name the fact that lacks `simulated: true`, before field errors hide which."""
        if isinstance(data, dict):
            for fact in data.get("facts") or []:
                if isinstance(fact, dict) and fact.get("simulated") is not True:
                    raise ValueError(f"fact {fact.get('id')!r} is not marked simulated: true")
        return data

    @model_validator(mode="after")
    def check(self) -> Self:
        ids = [fact.id for fact in self.facts]
        repeated = sorted({fact_id for fact_id in ids if ids.count(fact_id) > 1})
        if repeated:
            raise ValueError(f"fact IDs repeated: {repeated}")
        return self

    def fact(self, fact_id: str) -> Fact | None:
        return next((fact for fact in self.facts if fact.id == fact_id), None)

    def content_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


def load_media_kit(path: Path) -> MediaKit:
    raw = load_yaml(path)
    reject_contact_data(raw, path.name)
    try:
        kit = MediaKit.model_validate(raw)
    except (ValidationError, ValueError) as error:
        detail = error_text(error) if isinstance(error, ValidationError) else str(error)
        raise ConfigError(f"{path.name}: {detail}") from error
    if kit.publisher_id != path.stem:
        raise ConfigError(f"{path.name}: publisher_id {kit.publisher_id!r} differs from the file")
    return kit

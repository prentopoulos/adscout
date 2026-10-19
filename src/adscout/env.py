"""Read one setting from the environment or the gitignored `.env` file.

Secrets live in `.env` for local development (PROJECT.md §5). Each secret has one reader:
the model adapter reads the API key; the fetcher reads `ADSCOUT_CONTACT`. Values are
never printed or logged.
"""

import os
from pathlib import Path

from adscout.ids import ROOT

ENV_FILE = ROOT / ".env"


def env_value(name: str, env_file: Path = ENV_FILE) -> str | None:
    """The process environment's value, else the `.env` file's, else None."""
    value = os.environ.get(name)
    if value:
        return value
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, _, raw = text.removeprefix("export ").partition("=")
        if key.strip() == name:
            found = raw.strip()
            if len(found) >= 2 and found[0] == found[-1] and found[0] in "\"'":
                found = found[1:-1]
            return found or None
    return None

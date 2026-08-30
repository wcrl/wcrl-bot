"""Environment-backed configuration — env vars are the only config source.

TODO: none open.

Notes: `load()` fails fast so a misconfigured deploy never reaches the
Discord gateway. `guild_id=None` means "sync commands globally" (production
rollout only — see `.env.example`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when a required env var is missing or malformed."""


@dataclass(frozen=True)
class Config:
    bot_token: str
    registered_role_id: int
    officer_role_id: int
    team_category_id: int
    db_path: str
    guild_id: int | None = None


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is required but unset")
    return value


def _require_int(name: str) -> int:
    value = _require(name)
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a Discord snowflake ID, got {value!r}") from exc


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a Discord snowflake ID, got {value!r}") from exc


def load() -> Config:
    """Read config from the environment (and `.env` if present)."""
    load_dotenv()
    return Config(
        bot_token=_require("DISCORD_BOT_TOKEN"),
        registered_role_id=_require_int("REGISTERED_ROLE_ID"),
        officer_role_id=_require_int("OFFICER_ROLE_ID"),
        team_category_id=_require_int("TEAM_CATEGORY_ID"),
        guild_id=_optional_int("GUILD_ID"),
        db_path=os.getenv("DB_PATH", "data/wcrl.db").strip() or "data/wcrl.db",
    )

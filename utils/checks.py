"""Permission logic — the single home for access rules.

Current state: fully implemented (`is_registered`, `is_officer`).
TODO: none open.
Notes: cogs decorate commands with these rather than inspecting roles or
querying `competitors` inline. Checks raise `utils.errors` types so the
tree-level handler in `bot.py` renders one consistent message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from utils.errors import NotOfficer, NotRegistered

if TYPE_CHECKING:
    from bot import WCRLBot


async def has_competitor_row(bot: "WCRLBot", discord_id: int) -> bool:
    """Whether `discord_id` has a `competitors` row — the enforced definition of 'registered'."""
    row = await bot.db.fetch_one(
        "SELECT 1 FROM competitors WHERE discord_id = ?",
        (discord_id,),
    )
    return row is not None


def is_registered():
    """Command check: invoker has registered."""

    async def predicate(interaction: discord.Interaction) -> bool:
        bot: "WCRLBot" = interaction.client  # type: ignore[assignment]
        if not await has_competitor_row(bot, interaction.user.id):
            raise NotRegistered()
        return True

    return app_commands.check(predicate)


def is_officer():
    """Command check: invoker holds the Executive role."""

    async def predicate(interaction: discord.Interaction) -> bool:
        bot: "WCRLBot" = interaction.client  # type: ignore[assignment]
        member = interaction.user
        if not isinstance(member, discord.Member):
            # DM or uncached user — no roles to inspect.
            raise NotOfficer()
        if not any(role.id == bot.config.officer_role_id for role in member.roles):
            raise NotOfficer()
        return True

    return app_commands.check(predicate)

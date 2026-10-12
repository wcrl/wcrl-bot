"""Permission logic — the single home for access rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from utils.errors import NotOfficer, NotRegistered

if TYPE_CHECKING:
    from bot import WCRLBot


async def has_competitor_row(bot: "WCRLBot", discord_id: int) -> bool:
    """Whether `discord_id` has a `competitors` row — the enforced definition of 'registered'."""
    return await bot.db.competitors.exists(discord_id)


def is_registered():
    """Command check: invoker has registered."""

    async def predicate(interaction: discord.Interaction) -> bool:
        bot: "WCRLBot" = interaction.client  # type: ignore[assignment]
        if not await has_competitor_row(bot, interaction.user.id):
            raise NotRegistered()
        return True

    return app_commands.check(predicate)


def member_is_officer(bot: "WCRLBot", user: object) -> bool:
    """Whether `user` is a guild member holding the Executive role."""
    return isinstance(user, discord.Member) and any(
        role.id == bot.config.officer_role_id for role in user.roles
    )


def is_officer():
    """Command check: invoker holds the Executive role."""

    async def predicate(interaction: discord.Interaction) -> bool:
        bot: "WCRLBot" = interaction.client  # type: ignore[assignment]
        if not member_is_officer(bot, interaction.user):
            raise NotOfficer()
        return True

    return app_commands.check(predicate)

"""Discord role and channel provisioning for teams.

Current state: fully implemented.
TODO: none open.
Notes: this is the discord.py boundary CLAUDE.md's architecture principle
refers to — `cogs/teams.py` holds policy, this only executes it. Future
cogs (inventory, loans) should add their own service module the same way
rather than reaching for discord.py directly. Channels have no color in the
Discord API, so "team color" is the role's color instead — randomized on
creation.
"""

from __future__ import annotations

import logging

import discord

log = logging.getLogger(__name__)


class RoleService:
    """Creates and tears down the role + private channel backing a team."""

    def __init__(self, guild: discord.Guild, officer_role_id: int, team_category_id: int) -> None:
        self.guild = guild
        self.officer_role_id = officer_role_id
        self.team_category_id = team_category_id

    async def create_team_role(self, team_name: str) -> discord.Role:
        """Create the team's Discord role, with a randomized color."""
        return await self.guild.create_role(
            name=team_name,
            colour=discord.Colour.random(),
            mentionable=True,
            reason=f"WCRL team '{team_name}' created",
        )

    async def create_team_channel(
        self, channel_name: str, team_role: discord.Role
    ) -> discord.TextChannel:
        """Create the team's private text channel under TEAM_CATEGORY_ID (view access: team role + officer role)."""
        overwrites: dict[discord.Role, discord.PermissionOverwrite] = {
            self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            team_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }

        officer_role = self.guild.get_role(self.officer_role_id)
        if officer_role is not None:
            overwrites[officer_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True
            )

        category = self.guild.get_channel(self.team_category_id)
        if not isinstance(category, discord.CategoryChannel):
            log.warning("TEAM_CATEGORY_ID %s is not a category in this guild", self.team_category_id)
            category = None

        return await self.guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"WCRL private channel for role '{team_role.name}'",
        )

    async def add_member(self, member: discord.Member, role: discord.Role) -> None:
        await member.add_roles(role, reason="Joined WCRL team")

    async def remove_member(self, member: discord.Member, role: discord.Role) -> None:
        await member.remove_roles(role, reason="Left WCRL team")

    async def delete_team(self, role_id: int, channel_id: int) -> None:
        """Delete a team's role and channel, tolerating either already being gone."""
        role = self.guild.get_role(role_id)
        if role is not None:
            await role.delete(reason="WCRL team disbanded")

        channel = self.guild.get_channel(channel_id)
        if channel is not None:
            await channel.delete(reason="WCRL team disbanded")

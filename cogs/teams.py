"""Team management: the `/team` command group.

Current state: fully implemented — create/join/leave/list/roster/kick/
disband, including rollback of orphaned Discord objects on a failed create,
a confirm/cancel gate on disband, and an officer ping in the team's own
channel when leave/kick empties it.
TODO: none open.
Notes: teams are Discord-only, no external roster. One team per competitor
in v1, enforced by the `team_members.discord_id` unique index. Command
bodies that touch discord.py objects aren't unit tested — see
`tests/test_teams.py` for what's covered (name validation/normalization, DB
lookups).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

from db.connection import Database
from services.roles import RoleService
from utils.checks import is_officer, is_registered
from utils.errors import AlreadyOnTeam, InvalidTeamName, NotOnTeam, TeamNameTaken, TeamNotFound

if TYPE_CHECKING:
    from bot import WCRLBot

log = logging.getLogger(__name__)

NAME_MIN_LENGTH = 3
NAME_MAX_LENGTH = 32


def normalize_team_name(name: str) -> str:
    """Case/whitespace-insensitive key for `teams.name_normalized`."""
    return " ".join(name.split()).casefold()


def slugify_team_name(name: str) -> str:
    """Derive a Discord channel name from a team name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return slug[:90]


def validate_team_name(name: str) -> str:
    """Return the cleaned display name, or raise InvalidTeamName."""
    cleaned = " ".join(name.split())
    if not NAME_MIN_LENGTH <= len(cleaned) <= NAME_MAX_LENGTH:
        raise InvalidTeamName()
    if not re.search(r"[a-z0-9]", cleaned.casefold()):
        raise InvalidTeamName()
    return cleaned


async def team_for_member(db: Database, discord_id: int) -> aiosqlite.Row | None:
    """The caller's team row, or None if they aren't on one."""
    return await db.fetch_one(
        """
        SELECT teams.* FROM teams
        JOIN team_members ON team_members.team_id = teams.team_id
        WHERE team_members.discord_id = ?
        """,
        (discord_id,),
    )


async def team_by_name(db: Database, name: str) -> aiosqlite.Row | None:
    """Look up a team by display name (case/whitespace-insensitive)."""
    return await db.fetch_one(
        "SELECT * FROM teams WHERE name_normalized = ?", (normalize_team_name(name),)
    )


class DisbandConfirmView(discord.ui.View):
    """Confirm/cancel buttons gating `/team disband` — it's not reversible."""

    def __init__(self, invoker_id: int) -> None:
        super().__init__(timeout=30)
        self.invoker_id = invoker_id
        self.confirmed: bool = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                "Only the person who ran the command can confirm this.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Disband", style=discord.ButtonStyle.danger)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.confirmed = True
        self.stop()
        await interaction.response.edit_message(content="Disbanding...", view=None)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = False
        self.stop()
        await interaction.response.edit_message(content="Cancelled.", view=None)


class Teams(commands.GroupCog, name="team"):
    """`/team ...` — every subcommand lives here."""

    def __init__(self, bot: "WCRLBot") -> None:
        self.bot = bot

    async def _team_of(self, discord_id: int) -> aiosqlite.Row | None:
        return await team_for_member(self.bot.db, discord_id)

    async def _team_by_name(self, name: str) -> aiosqlite.Row | None:
        return await team_by_name(self.bot.db, name)

    async def _notify_if_empty(self, guild: discord.Guild, team: aiosqlite.Row) -> None:
        """Ping the officer role in the team's own channel if it just lost its last member.

        The team is deliberately not auto-disbanded — this just surfaces the
        decision to Executives instead of leaving an empty team unnoticed.
        """
        count = await self.bot.db.fetch_one(
            "SELECT COUNT(*) AS n FROM team_members WHERE team_id = ?", (team["team_id"],)
        )
        if count["n"] != 0:
            return

        channel = guild.get_channel(team["channel_id"])
        if channel is None:
            return

        await channel.send(
            f"<@&{self.bot.config.officer_role_id}> **{team['name']}** has no members left. "
            "What would you like to do with it?",
            allowed_mentions=discord.AllowedMentions(roles=True),
        )

    @app_commands.command(name="create", description="Create a new team.")
    @app_commands.describe(name="Team name (3-32 characters).")
    @is_registered()
    async def create(self, interaction: discord.Interaction, name: str) -> None:
        display_name = validate_team_name(name)

        if await self._team_of(interaction.user.id) is not None:
            raise AlreadyOnTeam()
        if await self._team_by_name(display_name) is not None:
            raise TeamNameTaken()

        # Discord objects come first (their IDs are NOT NULL columns); roll back both on any failure below.
        role_service = RoleService(
            interaction.guild, self.bot.config.officer_role_id, self.bot.config.team_category_id
        )
        role = await role_service.create_team_role(display_name)
        try:
            channel = await role_service.create_team_channel(
                slugify_team_name(display_name), role
            )
        except Exception:
            await role.delete(reason="team creation failed")
            raise

        try:
            await self.bot.db.execute(
                """
                INSERT INTO teams (name, name_normalized, role_id, channel_id, created_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    display_name,
                    normalize_team_name(display_name),
                    role.id,
                    channel.id,
                    interaction.user.id,
                ),
            )
            team = await self._team_by_name(display_name)
            await self.bot.db.execute(
                "INSERT INTO team_members (team_id, discord_id) VALUES (?, ?)",
                (team["team_id"], interaction.user.id),
            )
        except aiosqlite.IntegrityError:
            await role_service.delete_team(role.id, channel.id)
            raise TeamNameTaken()
        except Exception:
            await role_service.delete_team(role.id, channel.id)
            raise

        await role_service.add_member(interaction.user, role)
        await interaction.response.send_message(
            f"Team **{display_name}** created — check out {channel.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="join", description="Join an existing team.")
    @app_commands.describe(name="Name of the team to join.")
    @is_registered()
    async def join(self, interaction: discord.Interaction, name: str) -> None:
        if await self._team_of(interaction.user.id) is not None:
            raise AlreadyOnTeam()

        team = await self._team_by_name(name)
        if team is None:
            raise TeamNotFound()

        await self.bot.db.execute(
            "INSERT INTO team_members (team_id, discord_id) VALUES (?, ?)",
            (team["team_id"], interaction.user.id),
        )

        role = interaction.guild.get_role(team["role_id"])
        if role is not None and isinstance(interaction.user, discord.Member):
            await interaction.user.add_roles(role, reason="Joined WCRL team")

        await interaction.response.send_message(
            f"Joined **{team['name']}**.", ephemeral=True
        )

    @app_commands.command(name="leave", description="Leave your current team.")
    @is_registered()
    async def leave(self, interaction: discord.Interaction) -> None:
        team = await self._team_of(interaction.user.id)
        if team is None:
            raise NotOnTeam()

        await self.bot.db.execute(
            "DELETE FROM team_members WHERE discord_id = ?", (interaction.user.id,)
        )

        role = interaction.guild.get_role(team["role_id"])
        if role is not None and isinstance(interaction.user, discord.Member):
            await interaction.user.remove_roles(role, reason="Left WCRL team")

        await interaction.response.send_message(
            f"Left **{team['name']}**.", ephemeral=True
        )
        await self._notify_if_empty(interaction.guild, team)

    @app_commands.command(name="list", description="List all teams.")
    async def list_teams(self, interaction: discord.Interaction) -> None:
        rows = await self.bot.db.fetch_all(
            """
            SELECT teams.name, COUNT(team_members.discord_id) AS member_count
            FROM teams
            LEFT JOIN team_members ON team_members.team_id = teams.team_id
            GROUP BY teams.team_id
            ORDER BY teams.name COLLATE NOCASE
            """
        )
        if not rows:
            await interaction.response.send_message("No teams yet.", ephemeral=True)
            return

        lines = [
            f"**{row['name']}** — {row['member_count']} member"
            f"{'s' if row['member_count'] != 1 else ''}"
            for row in rows
        ]
        embed = discord.Embed(title="WCRL Teams", description="\n".join(lines))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roster", description="Show a team's members.")
    @app_commands.describe(name="Team name. Defaults to your own team.")
    async def roster(self, interaction: discord.Interaction, name: str | None = None) -> None:
        if name is None:
            team = await self._team_of(interaction.user.id)
            if team is None:
                raise NotOnTeam()
        else:
            team = await self._team_by_name(name)
            if team is None:
                raise TeamNotFound()

        members = await self.bot.db.fetch_all(
            """
            SELECT competitors.discord_id, competitors.full_name
            FROM team_members
            JOIN competitors ON competitors.discord_id = team_members.discord_id
            WHERE team_members.team_id = ?
            ORDER BY team_members.joined_at
            """,
            (team["team_id"],),
        )
        description = "\n".join(
            f"{row['full_name']} (<@{row['discord_id']}>)" for row in members
        ) or "No members."
        embed = discord.Embed(title=f"{team['name']} roster", description=description)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="kick", description="Remove a member from their team.")
    @app_commands.describe(member="The member to remove.")
    @is_officer()
    async def kick(self, interaction: discord.Interaction, member: discord.Member) -> None:
        team = await self._team_of(member.id)
        if team is None:
            raise NotOnTeam()

        await self.bot.db.execute(
            "DELETE FROM team_members WHERE discord_id = ?", (member.id,)
        )

        role = interaction.guild.get_role(team["role_id"])
        if role is not None:
            await member.remove_roles(role, reason=f"Kicked by {interaction.user}")

        log.info(
            "officer %s kicked %s from team %s", interaction.user.id, member.id, team["name"]
        )
        await interaction.response.send_message(
            f"Removed {member.mention} from **{team['name']}**.", ephemeral=True
        )
        await self._notify_if_empty(interaction.guild, team)

    @app_commands.command(name="disband", description="Delete a team entirely.")
    @app_commands.describe(name="Name of the team to disband.")
    @is_officer()
    async def disband(self, interaction: discord.Interaction, name: str) -> None:
        team = await self._team_by_name(name)
        if team is None:
            raise TeamNotFound()

        view = DisbandConfirmView(interaction.user.id)
        await interaction.response.send_message(
            f"Disband **{team['name']}**? This deletes its role, channel, and roster. "
            "This cannot be undone.",
            view=view,
            ephemeral=True,
        )
        await view.wait()

        if not view.confirmed:
            return

        role_service = RoleService(
            interaction.guild, self.bot.config.officer_role_id, self.bot.config.team_category_id
        )
        await role_service.delete_team(team["role_id"], team["channel_id"])
        # team_members rows cascade via ON DELETE CASCADE (PRAGMA foreign_keys=ON).
        await self.bot.db.execute("DELETE FROM teams WHERE team_id = ?", (team["team_id"],))

        log.info("officer %s disbanded team %s", interaction.user.id, team["name"])
        await interaction.followup.send(f"**{team['name']}** has been disbanded.", ephemeral=True)


async def setup(bot: "WCRLBot") -> None:
    await bot.add_cog(Teams(bot))

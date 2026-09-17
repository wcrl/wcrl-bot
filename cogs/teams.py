"""Team management: the `/team` command group.

Current state: fully implemented — create/join/leave/list/roster/kick/
disband, including rollback of orphaned Discord objects on a failed create,
a confirm/cancel gate on disband, and an officer ping (with a one-click
disband button) in the team's own channel when leave/kick empties it.
join/roster/disband autocomplete the team name from existing teams. A new
team's channel gets a welcome embed sourced from `content/DEFAULT_MESSAGE.md`.
TODO: none open.
Notes: teams are Discord-only, no external roster. One team per competitor
in v1, enforced by the `team_members.discord_id` unique index. Command
bodies that touch discord.py objects aren't unit tested — see
`tests/test_teams.py` for what's covered (name validation/normalization, DB
lookups, autocomplete). `EmptyTeamView` is a persistent view (registered in
`setup()`); its button resolves the team from the channel it sits in, so it
survives a bot restart. The welcome message is skipped silently (logged
instead) if `DEFAULT_MESSAGE.md` is missing or the bot can't post it — same
best-effort posture as the nickname set in `cogs/registration.py`.
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
from services.content import DEFAULT_MESSAGE_PATH, read_content_file
from services.roles import RoleService
from utils.checks import is_officer, is_registered, member_is_officer
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


async def team_by_channel(db: Database, channel_id: int) -> aiosqlite.Row | None:
    """Look up a team by its private channel id."""
    return await db.fetch_one(
        "SELECT * FROM teams WHERE channel_id = ?", (channel_id,)
    )


async def disband_team(bot: "WCRLBot", guild: discord.Guild, team: aiosqlite.Row) -> None:
    """Delete a team's Discord role, channel, and every DB row backing it."""
    role_service = RoleService(
        guild, bot.config.officer_role_id, bot.config.team_category_id
    )
    await role_service.delete_team(team["role_id"], team["channel_id"])
    # team_members rows cascade via ON DELETE CASCADE (PRAGMA foreign_keys=ON).
    await bot.db.execute("DELETE FROM teams WHERE team_id = ?", (team["team_id"],))


async def team_name_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Suggest existing team names as the invoker types a `name` argument."""
    bot: "WCRLBot" = interaction.client  # type: ignore[assignment]
    rows = await bot.db.fetch_all(
        """
        SELECT name FROM teams
        WHERE name LIKE ? ESCAPE '\\'
        ORDER BY name COLLATE NOCASE
        LIMIT 25
        """,
        (f"%{_escape_like(current)}%",),
    )
    return [app_commands.Choice(name=row["name"], value=row["name"]) for row in rows]


def _escape_like(text: str) -> str:
    """Escape LIKE wildcards so typed `%`/`_` match literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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


class EmptyTeamView(discord.ui.View):
    """One-click disband on the 'this team is empty' notice — Executives only.

    Persistent (no timeout, fixed custom_id) so the button keeps working after
    a bot restart; the team is resolved from the channel the notice sits in.
    """

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Disband team",
        style=discord.ButtonStyle.danger,
        custom_id="wcrl:disband_empty_team",
    )
    async def disband(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        bot: "WCRLBot" = interaction.client  # type: ignore[assignment]
        if not member_is_officer(bot, interaction.user):
            await interaction.response.send_message(
                "Only Executives can disband a team.", ephemeral=True
            )
            return

        team = await team_by_channel(bot.db, interaction.channel_id)
        if team is None:
            await interaction.response.edit_message(
                content="This team has already been disbanded.", view=None
            )
            return

        await interaction.response.send_message(
            f"Disbanding **{team['name']}**…", ephemeral=True
        )
        await disband_team(bot, interaction.guild, team)
        log.info(
            "officer %s disbanded empty team %s via button", interaction.user.id, team["name"]
        )


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
            "Disband it with the button below, or leave it and sort it out here.",
            view=EmptyTeamView(),
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
        # Respond first — slash commands have a tight 3-second initial-response
        # window, and the welcome post is a non-critical extra HTTP round-trip.
        await interaction.response.send_message(
            f"Team **{display_name}** created — check out {channel.mention}.",
            ephemeral=True,
        )
        await self._post_welcome_message(channel, display_name)

    async def _post_welcome_message(self, channel: discord.TextChannel, team_name: str) -> None:
        """Post the new team's welcome embed (content/DEFAULT_MESSAGE.md), best-effort."""
        text = read_content_file(DEFAULT_MESSAGE_PATH)
        if text is None:
            return

        embed = discord.Embed(
            title=f"Welcome to {team_name}!",
            description=text,
            color=discord.Color.blurple(),
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            log.warning("could not post welcome message in new team channel %s", channel.id)

    @app_commands.command(name="join", description="Join an existing team.")
    @app_commands.describe(name="Name of the team to join.")
    @app_commands.autocomplete(name=team_name_autocomplete)
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
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="roster", description="Show a team's members.")
    @app_commands.describe(name="Team name. Defaults to your own team.")
    @app_commands.autocomplete(name=team_name_autocomplete)
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
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
    @app_commands.autocomplete(name=team_name_autocomplete)
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

        await disband_team(self.bot, interaction.guild, team)

        log.info("officer %s disbanded team %s", interaction.user.id, team["name"])
        await interaction.followup.send(f"**{team['name']}** has been disbanded.", ephemeral=True)


async def setup(bot: "WCRLBot") -> None:
    bot.add_view(EmptyTeamView())
    await bot.add_cog(Teams(bot))

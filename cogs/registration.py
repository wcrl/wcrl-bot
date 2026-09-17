"""Competitor registration: the `/register` modal and `/status` command.

Current state: fully implemented — the modal upserts `competitors` and
`competitor_profiles` and grants the Competitor role; `/status` reports it
back, including which academic info (if any) is still missing.
TODO: decide with the exec team whether to hard-restrict registration to a
school email domain (currently any well-formed address is accepted).
Notes: fully self-contained in Discord, no external form or sheet. Never
log `school_email`. The DB row is written before the role/nickname are
applied, so a failure after the write still leaves the user usable via
`is_registered()`; the reverse order could leave a role with no row.

Year/major are dropdowns (`discord.ui.Select` wrapped in `discord.ui.Label`,
Discord's "Components V2" modal fields) rather than free text, so answers
stay consistent across competitors instead of splintering into "CS" /
"Computer Science" / "Comp Sci". They live in `competitor_profiles`, a
separate table from `competitors` (see schema.sql) — that's what lets
existing competitors pick this up by simply re-running `/register` rather
than needing a one-time data migration; a missing row there just means the
competitor hasn't supplied it yet. Re-running `/register` pre-fills the
modal from whatever is already on file.
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
from utils.errors import EmailAlreadyClaimed, InvalidEmail

if TYPE_CHECKING:
    from bot import WCRLBot

log = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

YEAR_OPTIONS = ["Freshman", "Sophomore", "Junior", "Senior", "Grad Student"]

MAJOR_OPTIONS = [
    "Mechanical Engineering",
    "Electrical Engineering",
    "Computer Science",
    "Computer Engineering",
    "Biomedical Engineering",
    "EDD",
    "Industrial Systems Engineering",
    "Harpur",
    "School of Management",
    "Other",
]


def _clean_email(raw: str) -> str:
    email = raw.strip().lower()
    if not _EMAIL_RE.match(email):
        raise InvalidEmail()
    return email


async def upsert_competitor(
    db: Database, discord_id: int, full_name: str, school_email: str
) -> tuple[aiosqlite.Row, bool]:
    """Insert or refresh a competitor's row; returns (row, is_new)."""
    full_name = full_name.strip()
    email = _clean_email(school_email)

    # school_email is COLLATE NOCASE in the schema — this compare is already case-insensitive.
    email_owner = await db.fetch_one(
        "SELECT discord_id FROM competitors WHERE school_email = ?", (email,)
    )
    if email_owner is not None and email_owner["discord_id"] != discord_id:
        raise EmailAlreadyClaimed()

    existing_account = await db.fetch_one(
        "SELECT 1 FROM competitors WHERE discord_id = ?", (discord_id,)
    )
    is_new = existing_account is None

    await db.execute(
        """
        INSERT INTO competitors (discord_id, full_name, school_email)
        VALUES (?, ?, ?)
        ON CONFLICT (discord_id) DO UPDATE
            SET full_name = excluded.full_name, school_email = excluded.school_email
        """,
        (discord_id, full_name, email),
    )
    row = await db.fetch_one("SELECT * FROM competitors WHERE discord_id = ?", (discord_id,))
    return row, is_new


async def upsert_profile(db: Database, discord_id: int, year: str, major: str) -> aiosqlite.Row:
    """Insert or refresh a competitor's year/major; returns the resulting row."""
    await db.execute(
        """
        INSERT INTO competitor_profiles (discord_id, year, major, updated_at)
        VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT (discord_id) DO UPDATE
            SET year = excluded.year, major = excluded.major, updated_at = excluded.updated_at
        """,
        (discord_id, year, major),
    )
    return await db.fetch_one(
        "SELECT * FROM competitor_profiles WHERE discord_id = ?", (discord_id,)
    )


class RegistrationModal(discord.ui.Modal, title="WCRL Competitor Registration"):
    full_name = discord.ui.Label(
        text="Full Name",
        component=discord.ui.TextInput(
            placeholder="Jane Doe",
            min_length=2,
            max_length=100,
        ),
    )
    school_email = discord.ui.Label(
        text="School Email",
        component=discord.ui.TextInput(
            placeholder="you@binghamton.edu",
            min_length=5,
            max_length=254,
        ),
    )
    year = discord.ui.Label(
        text="Year",
        component=discord.ui.Select(
            placeholder="Select your year",
            options=[discord.SelectOption(label=option, value=option) for option in YEAR_OPTIONS],
        ),
    )
    major = discord.ui.Label(
        text="Major",
        component=discord.ui.Select(
            placeholder="Select your major",
            options=[discord.SelectOption(label=option, value=option) for option in MAJOR_OPTIONS],
        ),
    )

    def __init__(
        self,
        bot: "WCRLBot",
        existing: aiosqlite.Row | None = None,
        existing_profile: aiosqlite.Row | None = None,
    ) -> None:
        super().__init__()
        self.bot = bot

        # Pre-fill from whatever is already on file, so re-running /register
        # to add a missing year/major doesn't force retyping name/email.
        # Must happen after super().__init__() — that's what deep-copies the
        # class-level items into per-instance ones; mutating earlier would
        # leak across every modal instance.
        if existing is not None:
            self.full_name.component.default = existing["full_name"]
            self.school_email.component.default = existing["school_email"]
        if existing_profile is not None:
            for option in self.year.component.options:
                option.default = option.value == existing_profile["year"]
            for option in self.major.component.options:
                option.default = option.value == existing_profile["major"]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        row, is_new = await upsert_competitor(
            self.bot.db,
            interaction.user.id,
            self.full_name.component.value,
            self.school_email.component.value,
        )
        await upsert_profile(
            self.bot.db,
            interaction.user.id,
            self.year.component.values[0],
            self.major.component.values[0],
        )

        if isinstance(interaction.user, discord.Member):
            role = interaction.guild.get_role(self.bot.config.registered_role_id)
            if role is not None and role not in interaction.user.roles:
                await interaction.user.add_roles(role, reason="Completed /register")

            # Discord nicknames cap at 32 characters; the modal allows longer names.
            try:
                await interaction.user.edit(
                    nick=row["full_name"][:32], reason="Completed /register"
                )
            except discord.HTTPException:
                log.warning(
                    "could not set nickname for %s (role hierarchy or missing permission)",
                    interaction.user.id,
                )

        verb = "Registered" if is_new else "Updated your registration for"
        await interaction.response.send_message(
            f"{verb} **{row['full_name']}**.",
            ephemeral=True,
        )


class Registration(commands.Cog):
    def __init__(self, bot: "WCRLBot") -> None:
        self.bot = bot

    @app_commands.command(name="register", description="Register as a WCRL competitor.")
    async def register(self, interaction: discord.Interaction) -> None:
        existing = await self.bot.db.fetch_one(
            "SELECT * FROM competitors WHERE discord_id = ?", (interaction.user.id,)
        )
        existing_profile = await self.bot.db.fetch_one(
            "SELECT * FROM competitor_profiles WHERE discord_id = ?", (interaction.user.id,)
        )
        # Modals must be the first response — do not defer before send_modal.
        await interaction.response.send_modal(
            RegistrationModal(self.bot, existing, existing_profile)
        )

    @app_commands.command(name="status", description="Check your registration status.")
    async def status(self, interaction: discord.Interaction) -> None:
        row = await self.bot.db.fetch_one(
            "SELECT * FROM competitors WHERE discord_id = ?", (interaction.user.id,)
        )
        if row is None:
            embed = discord.Embed(
                title="Registration Status",
                description="You're not registered yet. Run `/register` to get started.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        profile = await self.bot.db.fetch_one(
            "SELECT * FROM competitor_profiles WHERE discord_id = ?", (interaction.user.id,)
        )
        embed = discord.Embed(title="Registration Status", color=discord.Color.blurple())
        embed.add_field(name="Name", value=row["full_name"], inline=True)
        embed.add_field(name="Registered Since", value=row["registered_at"], inline=True)
        if profile is None:
            embed.add_field(
                name="Year / Major",
                value="Not on file — run `/register` again to add them.",
                inline=False,
            )
        else:
            embed.add_field(name="Year", value=profile["year"], inline=True)
            embed.add_field(name="Major", value=profile["major"], inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: "WCRLBot") -> None:
    await bot.add_cog(Registration(bot))

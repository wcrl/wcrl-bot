"""Competitor registration: the `/register` modal and `/status` command.

Current state: fully implemented — the modal upserts `competitors` and
grants the Competitor role; `/status` reports it back.
TODO: decide with the exec team whether to hard-restrict registration to a
school email domain (currently any well-formed address is accepted).
Notes: fully self-contained in Discord, no external form or sheet. Never
log `school_email`. The DB row is written before the role/nickname are
applied, so a failure after the write still leaves the user usable via
`is_registered()`; the reverse order could leave a role with no row.
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


class RegistrationModal(discord.ui.Modal, title="WCRL Competitor Registration"):
    full_name = discord.ui.TextInput(
        label="Full Name",
        placeholder="Jane Doe",
        min_length=2,
        max_length=100,
        required=True,
    )
    school_email = discord.ui.TextInput(
        label="School Email",
        placeholder="you@binghamton.edu",
        min_length=5,
        max_length=254,
        required=True,
    )

    def __init__(self, bot: "WCRLBot") -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        row, is_new = await upsert_competitor(
            self.bot.db, interaction.user.id, self.full_name.value, self.school_email.value
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
        # Modals must be the first response — do not defer before send_modal.
        await interaction.response.send_modal(RegistrationModal(self.bot))

    @app_commands.command(name="status", description="Check your registration status.")
    async def status(self, interaction: discord.Interaction) -> None:
        row = await self.bot.db.fetch_one(
            "SELECT * FROM competitors WHERE discord_id = ?", (interaction.user.id,)
        )
        if row is None:
            await interaction.response.send_message(
                "You're not registered yet. Run `/register` to get started.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"You're registered as **{row['full_name']}** (since {row['registered_at']}).",
            ephemeral=True,
        )


async def setup(bot: "WCRLBot") -> None:
    await bot.add_cog(Registration(bot))

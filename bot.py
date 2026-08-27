"""Entrypoint: wires config, the database, and the cogs together.

Current state: fully implemented — connects the DB, loads all cogs, syncs
slash commands, and funnels every command error through utils.errors.
TODO: none open.
Notes: requires the "Server Members Intent" enabled in the Discord developer
portal (role assignment needs Member objects); message_content is not
requested since every command is a slash command. New feature domains
register by adding their cog to EXTENSIONS. Guild-scoped sync (GUILD_ID set)
gives near-instant propagation in dev; global sync is for production
rollout.

Run with `python bot.py` (or via docker compose).
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
from db.connection import Database
from utils.errors import BotError, user_message

log = logging.getLogger("wcrl")

EXTENSIONS = (
    "cogs.registration",
    "cogs.teams",
)


class WCRLBot(commands.Bot):
    def __init__(self, cfg: config.Config) -> None:
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = cfg
        self.db = Database(cfg.db_path)

    async def setup_hook(self) -> None:
        await self.db.connect()

        for extension in EXTENSIONS:
            await self.load_extension(extension)
            log.info("loaded %s", extension)

        if self.config.guild_id is not None:
            guild = discord.Object(id=self.config.guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("synced %d commands to guild %s", len(synced), self.config.guild_id)
        else:
            synced = await self.tree.sync()
            log.info("synced %d commands globally", len(synced))

        self.tree.on_error = self.on_app_command_error

    async def close(self) -> None:
        await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("connected as %s (%s)", self.user, getattr(self.user, "id", "?"))

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Single funnel for command failures — renders BotError subclasses, logs everything else."""
        message = user_message(error)

        unwrapped = error.original if isinstance(error, app_commands.CommandInvokeError) else error
        if not isinstance(unwrapped, BotError):
            log.exception(
                "unhandled error in /%s",
                interaction.command.qualified_name if interaction.command else "?",
                exc_info=error,
            )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            log.warning("could not deliver error message to the user")


async def main() -> None:
    discord.utils.setup_logging(level=logging.INFO)
    cfg = config.load()
    async with WCRLBot(cfg) as bot:
        await bot.start(cfg.bot_token)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

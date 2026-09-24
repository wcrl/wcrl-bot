"""Entrypoint: wires config, the database, and the cogs together.

Current state: fully implemented — connects the DB, loads all cogs, syncs
slash commands, funnels every command error through utils.errors, and posts
online/offline announcements (with a changelog blurb when there's a new
entry) to the channel configured by ANNOUNCEMENT_CHANNEL_ID.
TODO: none open.
Notes: requires the "Server Members Intent" enabled in the Discord developer
portal (role assignment needs Member objects); message_content is not
requested since every command is a slash command. New feature domains
register by adding their cog to EXTENSIONS. Guild-scoped sync (GUILD_ID set)
gives near-instant propagation in dev; global sync is for production
rollout.

`docker stop` sends SIGTERM, which by default kills the process without
running `close()` — the SIGTERM handler installed in `main()` routes that
signal into a normal `bot.close()` so the shutdown announcement actually
gets a chance to send. A hard crash or a killed/OOM'd container still skips
it; only a watchdog outside this process could catch that, and there isn't
one.

Run with `python bot.py` (or via docker compose).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

import discord
from discord import app_commands
from discord.ext import commands

import config
from db.connection import Database
from services.announcements import (
    Announcement,
    parse_latest_entry,
    should_announce,
    shutdown_announcement,
    startup_announcement,
)
from services.content import CHANGELOG_PATH, read_content_file
from utils.errors import BotError, user_message

log = logging.getLogger("wcrl")

EXTENSIONS = (
    "cogs.registration",
    "cogs.teams",
    "cogs.stats",
)


class WCRLBot(commands.Bot):
    def __init__(self, cfg: config.Config) -> None:
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config = cfg
        self.db = Database(cfg.db_path)
        self._announced_startup = False
        self._announced_shutdown = False

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
        # Both a caught SIGTERM and the bot's own `async with` context manager
        # call close() — guard so the shutdown announcement posts once, not twice.
        if not self._announced_shutdown:
            self._announced_shutdown = True
            await self._send_announcement(shutdown_announcement())
        await self.db.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("connected as %s (%s)", self.user, getattr(self.user, "id", "?"))
        # on_ready can fire again on a gateway reconnect — only announce once per process.
        if self._announced_startup:
            return
        self._announced_startup = True
        await self._announce_startup()

    async def _announce_startup(self) -> None:
        if self.config.announcement_channel_id is None:
            return

        heading = body = None
        changelog_text = read_content_file(CHANGELOG_PATH)
        if changelog_text is not None:
            entry = parse_latest_entry(changelog_text)
            if entry is not None:
                heading, body = entry
                last_announced = await self.db.fetch_one(
                    "SELECT value FROM bot_state WHERE key = 'last_announced_changelog'"
                )
                last_value = last_announced["value"] if last_announced is not None else None
                if not should_announce(heading, last_value):
                    heading = body = None

        sent = await self._send_announcement(startup_announcement(heading, body))
        # Only mark the entry as announced once it has actually gone out — a
        # failed send (missing permission, no channel yet) must not burn it.
        if sent and heading is not None:
            await self.db.execute(
                """
                INSERT INTO bot_state (key, value) VALUES ('last_announced_changelog', ?)
                ON CONFLICT (key) DO UPDATE SET value = excluded.value
                """,
                (heading,),
            )

    async def _send_announcement(self, announcement: Announcement) -> bool:
        """Post an Announcement as an embed — looks like an official post, not a chat line."""
        if self.config.announcement_channel_id is None:
            return False

        channel = self.get_channel(self.config.announcement_channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(self.config.announcement_channel_id)
            except discord.HTTPException:
                log.warning(
                    "could not resolve announcement channel %s",
                    self.config.announcement_channel_id,
                )
                return False

        embed = discord.Embed(
            title=announcement.title,
            description=announcement.description,
            color=announcement.color,
        )
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            log.warning("could not post announcement to %s", self.config.announcement_channel_id)
            return False
        return True

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
        loop = asyncio.get_running_loop()
        sigterm_task: asyncio.Task | None = None

        def _on_sigterm() -> None:
            nonlocal sigterm_task
            sigterm_task = loop.create_task(bot.close())

        # add_signal_handler isn't implemented on Windows' default event loop;
        # harmless to skip there since docker compose (the deploy target) is Linux.
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signal.SIGTERM, _on_sigterm)

        await bot.start(cfg.bot_token)

        if sigterm_task is not None:
            await sigterm_task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

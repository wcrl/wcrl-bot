"""Officer-facing `/data` command: a live snapshot of registration and team stats.

Current state: fully implemented.
TODO: none open.
Notes: intentionally **not** ephemeral — running `/data` is visible to the
whole channel, unlike `/status`/`/team list`/`/team roster`; a non-officer
running it still gets a private refusal (`NotOfficer` renders ephemerally
via `bot.py`'s tree-level error handler, unaffected by this command's own
reply not being ephemeral). "Team Breakdown" is capped at
`TEAM_BREAKDOWN_LIMIT` teams with a "…and N more" tail — an embed field
caps out at 1024 characters, and a growing club could plausibly cross that
line within a season; the other sections (Registration, By Year, By Major)
are bounded by construction (one line, or one per dropdown option) and
don't need the same guard.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from services.stats import collect_stats
from utils.checks import is_officer

if TYPE_CHECKING:
    from bot import WCRLBot

TEAM_BREAKDOWN_LIMIT = 15


def build_stats_embed(stats: dict) -> discord.Embed:
    """Render a stats dict (see `services.stats.collect_stats`) as a fielded embed."""
    embed = discord.Embed(title="WCRL Stats", color=discord.Color.blurple())

    embed.add_field(
        name="Registration",
        value=(
            f"Total competitors: **{stats['total_competitors']}**\n"
            f"Year/major on file: **{stats['with_profile']}**\n"
            f"Still need to `/register`: **{stats['missing_profile']}**"
        ),
        inline=False,
    )

    if stats["year_counts"]:
        embed.add_field(
            name="By Year",
            value="\n".join(f"{year}: **{count}**" for year, count in stats["year_counts"]),
            inline=True,
        )

    if stats["major_counts"]:
        embed.add_field(
            name="By Major",
            value="\n".join(f"{major}: **{count}**" for major, count in stats["major_counts"]),
            inline=True,
        )

    embed.add_field(
        name="Teams",
        value=(
            f"Total teams: **{stats['total_teams']}**\n"
            f"Competitors on a team: **{stats['competitors_on_a_team']}**\n"
            f"Competitors not on a team: **{stats['competitors_without_team']}**\n"
            f"Average team size: **{stats['avg_team_size']:.1f}**"
        ),
        inline=False,
    )

    if stats["teams"]:
        shown = stats["teams"][:TEAM_BREAKDOWN_LIMIT]
        lines = [f"{name}: **{count}** member{'s' if count != 1 else ''}" for name, count in shown]
        remaining = len(stats["teams"]) - len(shown)
        if remaining > 0:
            lines.append(f"…and {remaining} more")
        embed.add_field(name="Team Breakdown", value="\n".join(lines), inline=False)

    return embed


class Stats(commands.Cog):
    def __init__(self, bot: "WCRLBot") -> None:
        self.bot = bot

    @app_commands.command(name="data", description="Show registration and team stats.")
    @is_officer()
    async def data(self, interaction: discord.Interaction) -> None:
        stats = await collect_stats(self.bot.db)
        await interaction.response.send_message(embed=build_stats_embed(stats))


async def setup(bot: "WCRLBot") -> None:
    await bot.add_cog(Stats(bot))

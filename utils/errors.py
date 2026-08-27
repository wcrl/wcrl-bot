"""Error types and the single place errors become user-facing text.

Current state: fully implemented.
TODO: map the discord.py errors worth distinguishing (at minimum Forbidden
— bot role too low to manage a team role — and CommandOnCooldown) before
everything else falls through to the generic message.
Notes: subclassing AppCommandError (not Exception) matters — discord.py
re-raises those as-is, so they reach the tree error handler unwrapped
whether raised from a check or from inside a command callback. Cogs raise a
BotError subclass; the tree-level handler in `bot.py` calls `user_message()`
to render it — handlers should never build their own copy for failure
cases, add a case here instead.
"""

from __future__ import annotations

from discord import app_commands


class BotError(app_commands.AppCommandError):
    """Base for expected, user-correctable failures."""

    message = "Something went wrong. Please try again."

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class NotRegistered(BotError):
    message = "You need to run `/register` before using this command."


class NotOfficer(BotError):
    message = "That command is restricted to Executives."


class EmailAlreadyClaimed(BotError):
    message = "That email is already registered to a different Discord account. Contact an Executive if this is a mistake."


class InvalidEmail(BotError):
    message = "That doesn't look like a valid email address."


class AlreadyOnTeam(BotError):
    message = "You're already on a team. Use `/team leave` first."


class NotOnTeam(BotError):
    message = "You're not on a team yet."


class TeamNotFound(BotError):
    message = "No team by that name."


class TeamNameTaken(BotError):
    message = "A team with that name already exists."


class InvalidTeamName(BotError):
    message = "Team names must be 3-32 characters and contain at least one letter or number."


def user_message(error: BaseException) -> str:
    """Map any exception to the text shown to the invoker."""
    # app_commands wraps check failures; unwrap before matching.
    if isinstance(error, app_commands.CommandInvokeError):
        error = error.original

    if isinstance(error, BotError):
        return error.message

    return BotError.message

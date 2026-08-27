# WCRL Discord Bot

## Goal
Discord bot for a university combat robotics club automating competitor registration and team management (role + private channel per team). Future scope (not yet built): inventory management, parts requesting, battery loaning — architecture must not block adding these later.

## Tech Stack
- Python + discord.py (slash commands, `discord.ui.Modal` for `/register`, Cogs per feature domain)
- SQLite via `aiosqlite` (async — never call blocking `sqlite3` directly in a command handler)
- Docker container; no public inbound port needed (outbound-only: Discord gateway), so it can run on a free host now or a self-hosted club server later

## Architecture Principles
- One cog per feature domain (`registration.py`, `teams.py`; future `inventory.py` etc. follow the same pattern, never bolted onto existing cogs).
- `services/` wraps external dependencies (role/channel creation) behind narrow interfaces, testable without discord.py.
- `utils/checks.py` is the single home for permission logic (`is_registered()`, `is_officer()`).
- Schema changes are additive only — new features add new tables, never modify existing ones.

## Current Decisions (subject to change)
Calls made for now, not permanent constraints — revisit as the club's needs evolve.

**Registration**
- `/register` is a self-contained Discord modal (Full Name + school email) — no external form or spreadsheet.
- Any well-formed email is accepted; registration is not yet restricted to a specific school domain (open question for the exec team).
- Re-running `/register` overwrites the stored name/email for that Discord account (upsert, not append).
- An email can only belong to one Discord account — rejected only if claimed by a *different* account.
- "Registered" means "holds the Competitor role"; the `competitors` DB row is the enforced source of truth, but the two are meant to always match in practice.
- On successful registration, the invoker's server nickname is set to their submitted full name (best-effort — skipped silently if the bot lacks permission or hierarchy to change it).

**Teams**
- One team per competitor (DB unique index on `team_members.discord_id`) — trivially relaxed later if co-ed/multi-team competitors are allowed.
- Team names: 3-32 characters, case- and whitespace-insensitive uniqueness; the private channel name is a slugified version of the team name.
- A team's private channel is visible only to its team role and the Executive role, and is created under the category configured by `TEAM_CATEGORY_ID`.
- The team role gets a randomized color on creation — channels have no color in the Discord API, so this stands in as the "team color."
- Leaving a team (or being kicked) does not disband it, even if it becomes empty — only `/team disband` deletes a team. If it becomes empty, the bot posts in the team's own channel pinging the Executive role to decide what to do with it.
- `/team disband` requires an explicit confirm button since it deletes the role, channel, and roster.

## Coding Guidelines
- Minimize comments. Code should read clearly through naming and structure, not narration — don't restate what a line already says. A single `#` line above a genuinely confusing block or sequence (a non-obvious workaround, a subtle ordering constraint) is fine; that's the exception, not the default.
- Docstrings are welcome, but keep them to one concise line — what it does, not how or why.
- Every file opens with a module-level docstring covering:
  - **Purpose** — what the file is for, in a sentence or two.
  - **Current state** — what's implemented vs. still stubbed/partial.
  - **TODO** — concrete next steps that aren't done yet.
  - **Notes** — non-obvious constraints, gotchas, or decisions worth flagging to whoever touches the file next.

  ```python
  """One-line purpose.

  TODO: 
  ...

  NOTES:
  ...
  """
  ```

## Project Structure
```
wcrl-bot/
├── bot.py / config.py
├── Dockerfile / docker-compose.yml / .env.example
├── data/wcrl.db            # gitignored, needs a persistent volume in prod
├── db/connection.py, schema.sql
├── services/roles.py
├── cogs/registration.py, teams.py
├── utils/checks.py, errors.py
└── tests/
```

## Data Model
- `competitors(discord_id PK, full_name, school_email UNIQUE, registered_at, created_at)`
- `teams(team_id PK, name, name_normalized UNIQUE, role_id UNIQUE, channel_id UNIQUE, created_by FK, created_at)`
- `team_members(team_id FK, discord_id FK, joined_at)` + unique index on `discord_id` (one team per competitor)

## Commands
See [COMMANDS.md](./.claude/COMMANDS.md).

## Workflow
Every change follows the same loop: **create the change, then test it.**
1. Implement the change.
2. Add or update its tests in the existing suite under `tests/` — new schema constraints go in `tests/test_db.py`, feature logic gets its own `tests/test_<feature>.py`, both following the existing per-class pattern. Don't leave new behavior uncovered or start a parallel test setup.
3. Verify it actually builds (modules import cleanly) and the full suite passes (`pytest`) before reporting the change complete — don't rely on read-through alone.

## Config
Env vars only (see `.env.example`): `DISCORD_BOT_TOKEN`, `REGISTERED_ROLE_ID` (Competitor role), `OFFICER_ROLE_ID` (Executive role), `TEAM_CATEGORY_ID` (category new team channels are created under), `GUILD_ID`, `DB_PATH`. Never commit `.env`; never log the bot token or raw school emails.
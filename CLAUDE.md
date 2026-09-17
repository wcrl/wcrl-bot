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
- Schema changes are additive only — new features add new tables, never modify existing ones. This is forced by `db/connection.py::apply_schema()` replaying all of `schema.sql` on every startup (`CREATE TABLE IF NOT EXISTS` is idempotent; `ALTER TABLE` is not — it'd crash the second boot). One new table per *round* of new data is fine indefinitely, but this can't express a true modification (renaming/retyping a column, tightening a constraint). **When that's actually needed, revisit this** — the standard fix is numbered migration files plus a `schema_migrations` table tracking which have run, so each applies exactly once instead of being replayed blindly. More moving parts than today's approach, so don't build it preemptively — just don't reach for another bolt-on new table if what's actually needed is a modification.
- `content/` holds hand-edited text the bot reads at runtime (`CHANGELOG.md`, `DEFAULT_MESSAGE.md`) — editing what's posted never requires a code change or redeploy of logic, just an edit to the file.

## Current Decisions (subject to change)
Calls made for now, not permanent constraints — revisit as the club's needs evolve.

**Registration**
- `/register` is a self-contained Discord modal (Full Name, school email, Year, Major) — no external form or spreadsheet.
- Year and Major are dropdowns (`discord.ui.Select` wrapped in `discord.ui.Label`, Discord's "Components V2" modal fields), not free text, so answers stay consistent across competitors. Options are hardcoded in `cogs/registration.py` (`YEAR_OPTIONS`, `MAJOR_OPTIONS`); Discord caps a dropdown at 25 options.
- Year/major live in `competitor_profiles`, a table separate from `competitors` — added when the field was added, with no backfill of existing rows. A missing row there just means the competitor hasn't supplied it yet; re-running `/register` is how they fill it in, pre-filled from whatever's already on file.
- Any well-formed email is accepted; registration is not yet restricted to a specific school domain (open question for the exec team).
- Re-running `/register` overwrites the stored name/email/year/major for that Discord account (upsert, not append).
- An email can only belong to one Discord account — rejected only if claimed by a *different* account.
- "Registered" means "holds the Competitor role"; the `competitors` DB row is the enforced source of truth, but the two are meant to always match in practice.
- On successful registration, the invoker's server nickname is set to their submitted full name (best-effort — skipped silently if the bot lacks permission or hierarchy to change it).

**Announcements**
- The bot posts to the channel configured by `ANNOUNCEMENT_CHANNEL_ID` (optional — skipped if unset) when it comes online and when it goes offline, as an embed (colored border, title-cased title, trailing status emoji) rather than a plain message — reads as an official post, not a chat line.
- The online embed includes a changelog blurb when `content/CHANGELOG.md`'s topmost heading is a real version (never the `## Unreleased` WIP bucket) and hasn't already been announced (tracked in `bot_state`). See **Changelog & Versioning** below.
- Shutdown announcements only fire on a clean `close()`. `docker stop`'s SIGTERM is caught in `bot.py::main()` and routed into `close()`; a hard crash or killed container still skips the message — there's no external watchdog for that.
- A new team's channel gets a welcome embed sourced from `content/DEFAULT_MESSAGE.md`, posted verbatim (no templating) right after the channel is created.

**Teams**
- One team per competitor (DB unique index on `team_members.discord_id`) — trivially relaxed later if co-ed/multi-team competitors are allowed.
- Team names: 3-32 characters, case- and whitespace-insensitive uniqueness; the private channel name is a slugified version of the team name.
- A team's private channel is visible only to its team role and the Executive role, and is created under the category configured by `TEAM_CATEGORY_ID`.
- The team role gets a randomized color on creation — channels have no color in the Discord API, so this stands in as the "team color."
- Leaving a team (or being kicked) does not disband it, even if it becomes empty — only `/team disband` deletes a team. If it becomes empty, the bot posts in the team's own channel pinging the Executive role to decide what to do with it.
- `/team disband` requires an explicit confirm button since it deletes the role, channel, and roster.
- `/team list` and `/team roster` reply ephemerally (only the invoker sees it) so they don't clutter the channel.

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
├── content/CHANGELOG.md    # topmost `##` version entry is what gets announced on startup
├── content/DEFAULT_MESSAGE.md  # posted in a new team's channel on creation
├── Dockerfile / docker-compose.yml / .env.example
├── data/wcrl.db            # gitignored, needs a persistent volume in prod
├── db/connection.py, schema.sql
├── services/roles.py, announcements.py, content.py
├── cogs/registration.py, teams.py
├── utils/checks.py, errors.py
└── tests/
```

## Data Model
- `competitors(discord_id PK, full_name, school_email UNIQUE, registered_at, created_at)`
- `competitor_profiles(discord_id PK FK -> competitors, year, major, updated_at)` — optional, added post-launch; absence means not yet supplied, not enforced/backfilled
- `teams(team_id PK, name, name_normalized UNIQUE, role_id UNIQUE, channel_id UNIQUE, created_by FK, created_at)`
- `team_members(team_id FK, discord_id FK, joined_at)` + unique index on `discord_id` (one team per competitor)
- `bot_state(key PK, value)` — small internal k/v store; currently just `last_announced_changelog`

## Commands
See [COMMANDS.md](./.claude/COMMANDS.md).

## Workflow
Every change follows the same loop: **create the change, then test it.**
1. Implement the change.
2. Add or update its tests in the existing suite under `tests/` — new schema constraints go in `tests/test_db.py`, feature logic gets its own `tests/test_<feature>.py`, both following the existing per-class pattern. Don't leave new behavior uncovered or start a parallel test setup.
3. Verify it actually builds (modules import cleanly) and the full suite passes (`pytest`) before reporting the change complete — don't rely on read-through alone.
4. Add an entry for the change to `content/CHANGELOG.md` — see **Changelog & Versioning** below. Do this for every user-facing change, without being asked.

## Changelog & Versioning
- **Current version: v1.0** — the last version actually shipped. Update this line yourself only when the user says to release/bump (see below); never pick or bump it on your own judgment.
- `content/CHANGELOG.md` follows Keep a Changelog style: an `## Unreleased` heading at the top accumulates changes as they're made, across as many prompts or deploys as it takes. A change only gets its own real version heading (`## vX.Y`) once the user decides to ship it — Claude never assigns a version number unprompted.
- **For every user-facing change**: add a bullet under `## Unreleased` in `content/CHANGELOG.md`, filed under a relevant `### ` subheading (add a new one if none of the existing ones fit — e.g. `### Registration`, `### Teams`, `### Announcements`). Do this without being asked, every time.
- **When the user says to release/bump the version** (they give you the number — never invent one): rename `## Unreleased` to `## vX.Y` with that number, keeping everything already under it, then add a fresh empty `## Unreleased` heading above it for whatever comes next. Update **Current version** above to the number just released.
- The bot posts the topmost heading's content to `ANNOUNCEMENT_CHANNEL_ID` on startup — but only a real version heading, never `## Unreleased`, and only once (tracked in `bot_state`) per version. So restarts while `## Unreleased` is current post nothing, no matter how many changes piled up in the meantime; the whole accumulated bucket goes out together on the first deploy after the rename.
- `content/CHANGELOG.md` is public-facing — it gets posted to Discord verbatim. Write bullets for the people using the bot (competitors/officers), not for a future developer: plain language, no file paths, config var names, table/function names, or other internal implementation detail — only things a competitor would recognize (`/register`, `/team list` are fine; `content/DEFAULT_MESSAGE.md`, `upsert_profile`, `ANNOUNCEMENT_CHANNEL_ID` are not). This has already leaked once (a bullet named `content/DEFAULT_MESSAGE.md` directly) — reread the bullet you just wrote before adding it and cut anything an outsider wouldn't recognize.

## Config
Env vars only (see `.env.example`): `DISCORD_BOT_TOKEN`, `REGISTERED_ROLE_ID` (Competitor role), `OFFICER_ROLE_ID` (Executive role), `TEAM_CATEGORY_ID` (category new team channels are created under), `GUILD_ID`, `ANNOUNCEMENT_CHANNEL_ID` (optional — online/offline/changelog posts; announcements are skipped if unset), `DB_PATH`. Never commit `.env`; never log the bot token or raw school emails.
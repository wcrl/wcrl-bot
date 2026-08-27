# TODO

## Setup
- [x] `git init`
- [ ] Initial commit (repo has no commits yet)
- [x] Create Discord application + bot user, get token, invite to test server (`bot` + `applications.commands` scopes) — already connected to test/application server
- [x] Note the IDs of the existing **Competitor** (registered) and **Executive** (officer) roles — these already exist, do not recreate them
- [x] Confirm the bot's own role sits above **Competitor** (and above where team roles will land) in the role hierarchy, so it can assign Competitor and manage team roles — it does NOT need to be above Executive
- [x] Manually delete the old season's team channels/roles before rollout (bot has no cleanup command for pre-existing, non-DB-tracked teams)
- [x] Scaffold project structure (`bot.py`, `config.py`, `db/`, `services/`, `cogs/`, `utils/`, `tests/`)
- [x] `requirements.txt` (discord.py, aiosqlite, python-dotenv)
- [x] `.env.example` + `.env` (gitignored) with all required vars
- [x] `.gitignore` (`.env`, `data/*.db*`, `*.json`, `__pycache__/`, `.venv/`)

## Core: DB layer
- [x] `db/schema.sql` — `competitors`, `teams`, `team_members` tables + one-team-per-competitor unique index
- [x] `db/connection.py` — aiosqlite connection helper, `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, apply schema on startup

## Core: Registration
- [x] `cogs/registration.py` — `/register` modal (Full Name, school email), upsert logic, Registered role assignment + nickname set to full name, reject-on-conflicting-email logic
- [x] `/status` command
- [x] `utils/checks.py` — `is_registered()`, `is_officer()`
- [x] `utils/errors.py` — centralized error → user-facing message mapping

## Core: Teams
- [x] `services/roles.py` — generic "create role" / "create private channel" helpers
- [x] `cogs/teams.py` — `/team create`, `/team join`, `/team leave`, `/team list`, `/team roster`, `/team kick`, `/team disband`, officer ping in-channel when a team is left empty
- [x] Team name normalization (case-insensitive uniqueness, length cap, channel slug derivation)

## Testing
- [x] `test_db.py` — in-memory SQLite, unique constraints (email, team name, one-team-per-competitor), cascade delete on disband
- [x] `test_registration.py` — upsert logic (new vs. re-registration, conflicting email, email validation)
- [x] `test_teams.py` — name normalization/slug/validation, DB-only team lookups
- [ ] Manual test pass through every command per the verification plan in the full plan doc (`/register`, `/team` flows, permission rejections) — needs a live Discord server, not yet run

## Deployment
- [x] `Dockerfile` + `docker-compose.yml` (mount `./data` as a volume)
- [x] Guild-scoped command sync for dev (`GUILD_ID`)
- [ ] Pick a free host (Railway/Fly.io) or confirm self-hosting; attach a persistent volume for `data/`
- [x] Pin replica count to 1
- [ ] Pre-deploy checklist: `.env` not tracked, `.env.example` has no real secrets, `DB_PATH` on the mounted volume
- [ ] Switch slash command sync to global once ready for the full server

## Future (not in current scope)
- [ ] Design inventory management cog + schema
- [ ] Design parts requesting cog + schema
- [ ] Design battery loaning cog + schema

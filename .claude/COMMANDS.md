# Bot Commands

| Command | Access | Behavior |
|---|---|---|
| `/register` | anyone | Opens a modal (Full Name, school email). Upserts `competitors` keyed by the invoker's Discord ID, assigns the Competitor role. Re-running refreshes stored name/email. Rejects only if the email is already claimed by a **different** Discord ID. |
| `/status` | anyone | Shows whether the invoker is registered (i.e. holds the Competitor role and has a `competitors` DB row) and their registered name. |
| `/team create <name>` | registered only | Fails if the name (case-insensitive) already exists or the invoker is already on a team. Creates a DB row, a Discord role, and a private text channel (visible to the team role + Officer role only). |
| `/team join <name>` | registered only | Fails if the team doesn't exist or the invoker is already on a team. Grants the team role and channel access. |
| `/team leave` | registered only | Removes the invoker from their current team (role + DB row). The team itself is **not** auto-disbanded if left empty — if it becomes empty, the bot pings the Executive role in the team's channel. |
| `/team list` | anyone | Lists all team names with member counts. |
| `/team roster [name]` | anyone | Shows a team's members; defaults to the invoker's own team if `name` is omitted. |
| `/team kick <member>` | officer only | Removes a specified member from their team (role + DB row). If it leaves the team empty, the bot pings the Executive role in the team's channel. |
| `/team disband <name>` | officer only | Deletes the team's Discord role, channel, and all associated DB rows. |

## Permission checks (`utils/checks.py`)
- `is_registered()` — invoker's `discord_id` exists in the `competitors` table (DB is source of truth, not just the role). `REGISTERED_ROLE_ID` points at the existing **Competitor** role.
- `is_officer()` — invoker holds the `OFFICER_ROLE_ID` role. `OFFICER_ROLE_ID` points at the existing **Executive** role (assigned manually by server admins, outside the bot).

## Future commands (not built yet)
Placeholder for inventory management, parts requesting, and battery loaning — each will live in its own cog (`inventory.py`, `parts_requests.py`, `battery_loans.py`) with commands added here once designed.

# Changelog

New changes accumulate under `## Unreleased` below — that heading is never
announced, no matter how many times the bot restarts while it's current.
Once you decide it's time to ship, tell Claude a version number; it renames
`Unreleased` to that version and starts a fresh `Unreleased` section above
it. The bot then posts the newly-versioned section on its next startup.
See CLAUDE.md > Changelog & Versioning for the full mechanics.

## Unreleased

## v1.1
### Stats
- Officers can now run `/data` to see a snapshot of registration and team stats (how many competitors are registered, their year/major breakdown, team sizes).

## v1.0
### Registration
- `/register` now also asks for your year and major (dropdowns, so answers stay consistent instead of splintering into "CS" / "Computer Science" / "Comp Sci").
- Already registered? Just run `/register` again — it pre-fills what you already gave us and only asks you to fill in what's missing.
- `/status` now shows your year and major, and tells you if they're missing.

### Announcements
- The bot now posts here when it comes online or goes offline.
- New team channels now get a welcome message when the team is created.

### Teams
- `/team list` and `/team roster` replies are now private (only you see them) instead of posting to the whole channel.

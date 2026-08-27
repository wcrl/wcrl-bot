-- WCRL bot schema.
--
-- Changes are additive only: new features add new tables, existing tables are
-- never modified. Every statement here must be idempotent (IF NOT EXISTS) —
-- the whole file is replayed on every startup.

CREATE TABLE IF NOT EXISTS competitors (
    discord_id   INTEGER PRIMARY KEY,
    full_name    TEXT NOT NULL,
    school_email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    registered_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS teams (
    team_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    -- Lowercased/collapsed form of `name`; enforces case-insensitive uniqueness.
    name_normalized TEXT NOT NULL UNIQUE,
    role_id         INTEGER NOT NULL UNIQUE,
    channel_id      INTEGER NOT NULL UNIQUE,
    created_by      INTEGER NOT NULL REFERENCES competitors (discord_id),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id    INTEGER NOT NULL REFERENCES teams (team_id) ON DELETE CASCADE,
    discord_id INTEGER NOT NULL REFERENCES competitors (discord_id) ON DELETE CASCADE,
    joined_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (team_id, discord_id)
);

-- One team per competitor in v1. Drop this index to relax the rule later.
CREATE UNIQUE INDEX IF NOT EXISTS idx_team_members_one_team
    ON team_members (discord_id);

CREATE INDEX IF NOT EXISTS idx_team_members_team
    ON team_members (team_id);

-- ─────────────────────────────────────────────────────────────
-- NBL.GG  —  SQLite Schema  (v2)
-- Run via:  flask init-db
-- ─────────────────────────────────────────────────────────────

PRAGMA foreign_keys = ON;

-- ── TEAMS ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS teams (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT    NOT NULL UNIQUE,
    city     TEXT    NOT NULL,
    abbr     TEXT    NOT NULL,
    color    TEXT    NOT NULL DEFAULT '#ff7a00',
    logo     TEXT    NOT NULL DEFAULT '🏀',
    logo_url TEXT
);

-- ── PLAYERS ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS players (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT    NOT NULL,
    team_id  INTEGER NOT NULL REFERENCES teams(id) ON UPDATE CASCADE ON DELETE SET NULL,
    position TEXT    NOT NULL CHECK(position IN ('PG','SG','SF','PF','C'))
);

-- ── MATCHES ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS matches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    home_team_id INTEGER NOT NULL REFERENCES teams(id),
    away_team_id INTEGER NOT NULL REFERENCES teams(id),
    home_score   INTEGER,
    away_score   INTEGER,
    status       TEXT NOT NULL DEFAULT 'upcoming'
                      CHECK(status IN ('upcoming','completed','cancelled')),
    date         TEXT NOT NULL,
    stage        TEXT NOT NULL DEFAULT 'Regular Season'
);

-- ── PLAYER GAME STATS (full box score) ────────────────────────
CREATE TABLE IF NOT EXISTS player_game_stats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id   INTEGER REFERENCES players(id) ON DELETE CASCADE,
    match_id    INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team_id     INTEGER NOT NULL REFERENCES teams(id)   ON DELETE CASCADE,
    pts         INTEGER NOT NULL DEFAULT 0,
    fgm         INTEGER NOT NULL DEFAULT 0,
    fga         INTEGER NOT NULL DEFAULT 0,
    three_pm    INTEGER NOT NULL DEFAULT 0,
    three_pa    INTEGER NOT NULL DEFAULT 0,
    ftm         INTEGER NOT NULL DEFAULT 0,
    fta         INTEGER NOT NULL DEFAULT 0,
    ast         INTEGER NOT NULL DEFAULT 0,
    stl         INTEGER NOT NULL DEFAULT 0,
    blk         INTEGER NOT NULL DEFAULT 0,
    reb         INTEGER NOT NULL DEFAULT 0,
    tov         INTEGER NOT NULL DEFAULT 0,
    fls         INTEGER NOT NULL DEFAULT 0,
    plus_minus  INTEGER NOT NULL DEFAULT 0,
    is_walkon   BOOLEAN NOT NULL DEFAULT 0,
    walkon_name TEXT,
    UNIQUE(player_id, match_id),
    CHECK (
        (is_walkon = 1 AND player_id IS NULL AND walkon_name IS NOT NULL)
        OR
        (is_walkon = 0 AND player_id IS NOT NULL AND walkon_name IS NULL)
    )
);

-- ── TEAM RECORDS ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS team_records (
    team_id        INTEGER PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE,
    wins           INTEGER NOT NULL DEFAULT 0,
    losses         INTEGER NOT NULL DEFAULT 0,
    points_for     INTEGER NOT NULL DEFAULT 0,
    points_against INTEGER NOT NULL DEFAULT 0
);

-- ── ANNOUNCEMENTS ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS announcements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    order_index INTEGER NOT NULL DEFAULT 0
);

-- ── SITE SETTINGS ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS site_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS banner_announcements (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schedule_games (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    week      TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    status    TEXT NOT NULL DEFAULT 'pending'
              CHECK(status IN ('pending', 'completed'))
);

-- ─────────────────────────────────────────────────────────────
-- SEED DATA
-- ─────────────────────────────────────────────────────────────

INSERT OR IGNORE INTO teams (id, name, city, abbr, color, logo, logo_url) VALUES
    (1, 'Neon Wolves',    'New York',    'NW', '#00f0ff', '🐺', NULL),
    (2, 'Apex Surge',     'Los Angeles', 'AS', '#ff3c3c', '⚡', NULL),
    (3, 'Ghost Protocol', 'Chicago',     'GP', '#a855f7', '👻', NULL),
    (4, 'Iron Circuit',   'Houston',     'IC', '#f97316', '⚙️', NULL),
    (5, 'Solar Wraith',   'Miami',       'SW', '#eab308', '☀️', NULL),
    (6, 'Cryo Strike',    'Seattle',     'CS', '#06b6d4', '❄️', NULL),
    (7, 'Rogue Signal',   'Atlanta',     'RS', '#22c55e', '📡', NULL),
    (8, 'Dark Matter',    'Phoenix',     'DM', '#ec4899', '🌑', NULL);

INSERT OR IGNORE INTO players (id, name, team_id, position) VALUES
    (1,  'xShadowKing',   1, 'PG'), (2,  'BlazeFury99',   1, 'SG'),
    (3,  'VoidRunner',    1, 'SF'), (4,  'TitanGrip',     1, 'PF'),
    (5,  'CenterPulse',   1, 'C'),
    (6,  'ApexPred',      2, 'PG'), (7,  'LightningRod7', 2, 'SG'),
    (8,  'StormBreaker',  2, 'SF'), (9,  'IronWall22',    2, 'PF'),
    (10, 'DoomPost',      2, 'C'),
    (11, 'PhantomStep',   3, 'PG'), (12, 'GhostFlicker',  3, 'SG'),
    (13, 'SilentBlade',   3, 'SF'), (14, 'EchoFist',      3, 'PF'),
    (15, 'VoidAnchor',    3, 'C'),
    (16, 'CyberCore',     4, 'PG'), (17, 'WireFrame',     4, 'SG'),
    (18, 'GlitchShot',    4, 'SF'), (19, 'SteelPlate',    4, 'PF'),
    (20, 'PixelTower',    4, 'C'),
    (21, 'SunBurner',     5, 'PG'), (22, 'HeatMirage',    5, 'SG'),
    (23, 'ScorchWing',    5, 'SF'), (24, 'FlareKnuckle',  5, 'PF'),
    (25, 'InfernoPost',   5, 'C'),
    (26, 'FrostByte',     6, 'PG'), (27, 'IceDagger',     6, 'SG'),
    (28, 'BlizzardWing',  6, 'SF'), (29, 'GlacierFist',   6, 'PF'),
    (30, 'ArcticPillar',  6, 'C'),
    (31, 'StaticNoise',   7, 'PG'), (32, 'FreqJammer',    7, 'SG'),
    (33, 'WaveHacker',    7, 'SF'), (34, 'SignalBreak',   7, 'PF'),
    (35, 'DeadZone',      7, 'C'),
    (36, 'VoidPulse',     8, 'PG'), (37, 'DarkSpin',      8, 'SG'),
    (38, 'NullShift',     8, 'SF'), (39, 'AbyssCharge',   8, 'PF'),
    (40, 'EventHorizon',  8, 'C');

INSERT OR IGNORE INTO team_records (team_id, wins, losses, points_for, points_against) VALUES
    (1, 18, 4,  2340, 1980), (2, 16, 6,  2210, 2050),
    (3, 14, 8,  2100, 2000), (4, 13, 9,  2080, 2090),
    (5, 11, 11, 1990, 2010), (6, 9,  13, 1870, 2050),
    (7, 7,  15, 1760, 2120), (8, 4,  18, 1630, 2270);

INSERT OR IGNORE INTO matches
    (id, home_team_id, away_team_id, home_score, away_score, status, date, stage)
VALUES
    (1,  1, 2, 112, 98,   'completed', 'Apr 10, 2025', 'Week 12'),
    (2,  3, 4, 105, 101,  'completed', 'Apr 10, 2025', 'Week 12'),
    (3,  5, 6, 98,  95,   'completed', 'Apr 11, 2025', 'Week 12'),
    (4,  7, 8, 88,  79,   'completed', 'Apr 11, 2025', 'Week 12'),
    (5,  2, 3, 110, 104,  'completed', 'Apr 7,  2025', 'Week 11'),
    (6,  1, 6, 121, 88,   'completed', 'Apr 7,  2025', 'Week 11'),
    (7,  1, 3, NULL, NULL,'upcoming',  'Apr 18, 2025', 'Week 13'),
    (8,  2, 4, NULL, NULL,'upcoming',  'Apr 18, 2025', 'Week 13'),
    (9,  5, 8, NULL, NULL,'upcoming',  'Apr 19, 2025', 'Week 13'),
    (10, 6, 7, NULL, NULL,'upcoming',  'Apr 19, 2025', 'Week 13');

INSERT OR IGNORE INTO player_game_stats
    (player_id,match_id,team_id,pts,fgm,fga,three_pm,three_pa,ftm,fta,ast,stl,blk,reb,tov,fls,plus_minus) VALUES
    (1, 1,1,42,15,28,4,8, 8,9, 9,3,0,6, 2,2, 18),(2, 1,1,28,10,20,3,7, 5,6, 5,2,0,4, 1,3, 14),
    (3, 1,1,18, 7,15,1,3, 3,4, 3,1,1,7, 2,2,  8),(4, 1,1,14, 6,11,0,0, 2,3, 2,1,2,11,1,4, 10),
    (5, 1,1,10, 4, 7,0,0, 2,2, 1,0,3,14,0,2, 12),(6, 1,2,31,11,22,3,7, 6,7,10,2,0,4, 3,1,-18),
    (7, 1,2,25, 9,19,2,5, 5,6, 4,1,0,3, 2,2,-14),(8, 1,2,20, 7,16,1,4, 5,6, 3,1,1,5, 2,3, -8),
    (9, 1,2,12, 5,10,0,0, 2,3, 2,0,2,10,1,4,-10),(10,1,2,10, 4, 7,0,0, 2,2, 1,0,3,12,1,2,-12),
    (11,2,3,32,11,21,3,6, 7,8,12,2,0,5, 3,2,  4),(12,2,3,24, 9,18,2,5, 4,5, 4,2,0,3, 1,3,  4),
    (13,2,3,22, 8,17,1,4, 5,6, 3,1,1,7, 2,2,  4),(14,2,3,16, 6,12,0,0, 4,5, 2,1,2,10,1,4,  4),
    (15,2,3,11, 4, 8,0,0, 3,4, 1,0,4,15,0,2,  4),(16,2,4,28,10,20,2,5, 6,7, 9,1,0,4, 3,1, -4),
    (17,2,4,26, 9,18,3,7, 5,6, 5,2,0,3, 1,2, -4),(18,2,4,22, 8,16,1,3, 5,6, 3,1,1,6, 2,3, -4),
    (19,2,4,15, 5,10,0,0, 5,6, 2,0,2,11,1,4, -4),(20,2,4,10, 4, 7,0,0, 2,3, 1,0,3,13,1,2, -4),
    (6, 5,2,34,12,23,3,7, 7,8,11,2,0,5, 2,2,  6),(7, 5,2,28,10,20,3,6, 5,6, 5,2,0,4, 1,2,  6),
    (8, 5,2,23, 8,17,2,5, 5,6, 4,1,1,6, 2,3,  6),(9, 5,2,14, 5,10,0,0, 4,5, 2,0,2,12,1,4,  6),
    (10,5,2,11, 4, 7,0,0, 3,4, 1,0,3,13,0,2,  6),(11,5,3,30,11,21,2,5, 6,7,13,2,0,4, 3,2, -6),
    (12,5,3,22, 8,17,2,5, 4,5, 4,2,0,3, 1,3, -6),(13,5,3,20, 7,15,1,3, 5,6, 3,1,1,8, 2,2, -6),
    (14,5,3,18, 6,12,0,0, 6,7, 2,0,2,11,1,4, -6),(15,5,3,14, 5, 9,0,0, 4,5, 1,0,3,14,0,2, -6),
    (1, 6,1,38,14,26,4,9, 6,7,10,3,0,5, 1,2, 33),(2, 6,1,30,11,21,3,6, 5,6, 6,2,0,4, 1,2, 30),
    (3, 6,1,22, 8,16,1,3, 5,6, 3,1,1,8, 1,2, 28),(4, 6,1,18, 6,12,0,0, 6,7, 2,0,2,12,1,3, 25),
    (5, 6,1,13, 5, 8,0,0, 3,4, 1,0,4,15,0,2, 22),(26,6,6,22, 8,17,2,5, 4,5, 7,1,0,4, 3,2,-33),
    (27,6,6,20, 7,16,2,5, 4,5, 4,2,0,3, 2,3,-30),(28,6,6,18, 6,14,1,3, 5,6, 3,1,1,6, 2,2,-28),
    (29,6,6,14, 5,10,0,0, 4,5, 2,0,2,10,1,4,-25),(30,6,6,14, 5,10,0,0, 4,5, 1,0,2,12,1,2,-22);

INSERT OR IGNORE INTO announcements (id, message, created_at) VALUES
    (1, 'Season 4 playoffs begin May 2nd — don''t miss it!', 'Apr 10, 2025');

INSERT OR IGNORE INTO site_settings (key, value) VALUES
    ('banner_speed', '5'),
    ('banner_autoscroll', 'true'),
    ('current_week', 'Week 1'),
    ('current_week_deadline', '');

INSERT OR IGNORE INTO banner_announcements (id, message, created_at) VALUES
    (1, 'Season 4 playoffs begin May 2nd — don''t miss it!', 'Apr 10, 2025');

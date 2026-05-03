"""
db.py  —  SQLite connection helper for NBL.GG
────────────────────────────────────────────────
Usage inside a Flask route:
    from db import get_db, query, query_one, execute

    rows = query("SELECT * FROM teams ORDER BY name")
    team = query_one("SELECT * FROM teams WHERE id = ?", [team_id])
    execute("UPDATE players SET team_id = ? WHERE id = ?", [new_id, player_id])
"""

import sqlite3
import os
from flask import g

# Path to the SQLite database file (next to app.py)
DATABASE = os.path.join(os.path.dirname(__file__), "nbl.db")


# ── CONNECTION ────────────────────────────────────────────────
def get_db():
    """
    Return a per-request SQLite connection stored on Flask's 'g' object.
    Creates the connection on first call within a request context.
    """
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row   # rows behave like dicts: row["column"]
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")  # better concurrent read performance
        _ensure_walkon_stats_schema(g.db)
    return g.db


def _ensure_walkon_stats_schema(db: sqlite3.Connection):
    """
    Keep existing databases compatible with walk-on stat lines.
    Walk-ons need player_id to allow NULL plus two metadata columns.
    """
    cols = db.execute("PRAGMA table_info(player_game_stats)").fetchall()
    if not cols:
        return

    col_names = {col["name"] for col in cols}
    player_col = next((col for col in cols if col["name"] == "player_id"), None)
    needs_rebuild = (
        player_col is not None and player_col["notnull"] == 1
    ) or "is_walkon" not in col_names or "walkon_name" not in col_names

    if not needs_rebuild:
        return

    db.execute("PRAGMA foreign_keys = OFF")
    db.executescript("""
        DROP TABLE IF EXISTS player_game_stats_new;
        CREATE TABLE IF NOT EXISTS player_game_stats_new (
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
    """)
    db.execute("""
        INSERT INTO player_game_stats_new
            (id, player_id, match_id, team_id,
             pts, fgm, fga, three_pm, three_pa, ftm, fta,
             ast, stl, blk, reb, tov, fls, plus_minus,
             is_walkon, walkon_name)
        SELECT
            id, player_id, match_id, team_id,
            pts, fgm, fga, three_pm, three_pa, ftm, fta,
            ast, stl, blk, reb, tov, fls, plus_minus,
            0, NULL
        FROM player_game_stats
    """)
    db.executescript("""
        DROP TABLE player_game_stats;
        ALTER TABLE player_game_stats_new RENAME TO player_game_stats;
    """)
    db.execute("PRAGMA foreign_keys = ON")
    db.commit()


def close_db(e=None):
    """Tear down the connection at the end of every request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ── QUERY HELPERS ────────────────────────────────────────────
def query(sql: str, params=()) -> list[sqlite3.Row]:
    """Run a SELECT and return all matching rows."""
    return get_db().execute(sql, params).fetchall()


def query_one(sql: str, params=()) -> sqlite3.Row | None:
    """Run a SELECT and return the first row, or None."""
    return get_db().execute(sql, params).fetchone()


def execute(sql: str, params=()) -> sqlite3.Cursor:
    """
    Run an INSERT / UPDATE / DELETE.
    Commits automatically; returns the cursor so callers can read
    cursor.lastrowid when needed.
    """
    db  = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur


# ── INIT ──────────────────────────────────────────────────────
def init_db():
    """
    Drop-and-recreate all tables, then load seed data from schema.sql.
    Called by the  `flask init-db`  CLI command defined in app.py.
    """
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        db.executescript(f.read())

    db.commit()
    db.close()
    print(f"✓  Database initialised  →  {DATABASE}")


def register(app):
    """
    Call this once in app.py:
        import db
        db.register(app)

    This wires up teardown and the CLI command automatically.
    """
    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command():
        """Create tables and load seed data (destructive – re-run to reset)."""
        init_db()

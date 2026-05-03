import os
import csv
import re
import secrets
import requests
from urllib.parse import urlencode
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, session, redirect,
    url_for, request, flash, abort, g
)
import db as _db

app = Flask(__name__)

# ── REGISTER DB (teardown + CLI command) ─────────────────────
_db.register(app)

# ── SECRET KEY ────────────────────────────────────────────────
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

# ── DISCORD OAUTH2 CONFIG ────────────────────────────────────
DISCORD_CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID",     "YOUR_CLIENT_ID_HERE")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")
DISCORD_REDIRECT_URI  = os.environ.get("DISCORD_REDIRECT_URI",  "http://localhost:5000/callback")
DISCORD_API_BASE      = "https://discord.com/api/v10"
DISCORD_AUTH_URL      = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL     = "https://discord.com/api/oauth2/token"

# ── ADMIN CONFIG ─────────────────────────────────────────────
ADMIN_IDS = {
    "500424973383499776" # random
}

BANNER_DEFAULTS = {
    "banner_speed": "5",
    "banner_autoscroll": "true",
}

SCHEDULE_CSV_PATH = os.path.join(app.root_path, "templates", "[NBL] - Season 1  - Schedule.csv")

# ── AUTH HELPERS ──────────────────────────────────────────────
def get_current_user():
    return session.get("user")

def is_admin():
    user = get_current_user()
    return user is not None and str(user.get("id")) in ADMIN_IDS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            flash("You must be logged in to access that page.", "error")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            flash("You must be logged in.", "error")
            return redirect(url_for("home"))
        if not is_admin():
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _ensure_site_settings_table():
    _db.execute("""
        CREATE TABLE IF NOT EXISTS site_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)


def _set_site_setting(key, value):
    _ensure_site_settings_table()
    _db.execute(
        "INSERT INTO site_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        [key, value]
    )


def _get_site_setting(key, default=""):
    _ensure_site_settings_table()
    row = _db.query_one("SELECT value FROM site_settings WHERE key = ?", [key])
    return row["value"] if row else default


def _ensure_schedule_games_table():
    _db.execute("""
        CREATE TABLE IF NOT EXISTS schedule_games (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            week      TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            status    TEXT NOT NULL DEFAULT 'pending'
                      CHECK(status IN ('pending', 'completed'))
        )
    """)


def _week_number(week):
    match = re.search(r"\d+", week or "")
    return int(match.group(0)) if match else 0


def _normalize_week(week):
    week = (week or "").strip()
    if week.isdigit():
        return f"Round {week}"
    match = re.search(r"\b(?:Round|Week|R)\s*(\d+)\b", week, re.IGNORECASE)
    return f"Round {match.group(1)}" if match else week


def _read_schedule_csv_rows():
    if not os.path.exists(SCHEDULE_CSV_PATH):
        return []

    with open(SCHEDULE_CSV_PATH, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    for i, row in enumerate(rows):
        header = [cell.strip().lower() for cell in row]
        if {"week", "home_team", "away_team"}.issubset(set(header)):
            week_i = header.index("week")
            home_i = header.index("home_team")
            away_i = header.index("away_team")
            parsed = []
            for data in rows[i + 1:]:
                week = data[week_i].strip() if len(data) > week_i else ""
                home = data[home_i].strip() if len(data) > home_i else ""
                away = data[away_i].strip() if len(data) > away_i else ""
                if week and home and away:
                    parsed.append({"week": _normalize_week(week), "home_team": home, "away_team": away})
            return parsed

    parsed = []
    current_week = ""
    waiting_home = ""
    for row in rows:
        cells = [cell.strip() for cell in row]
        for cell in cells:
            week_match = re.search(r"\b(?:Round|Week|R)\s*\d+\b", cell, re.IGNORECASE)
            if week_match:
                current_week = _normalize_week(week_match.group(0))
                waiting_home = ""
                break

        if not current_week:
            continue

        team = cells[8] if len(cells) > 8 else ""
        if not team:
            continue

        lower = team.lower()
        if lower in {"final", "schedule", "nbl schedule"} or "deadline" in lower:
            continue
        if team.replace(".", "", 1).isdigit():
            continue

        if not waiting_home:
            waiting_home = team
        else:
            parsed.append({"week": current_week, "home_team": waiting_home, "away_team": team})
            waiting_home = ""

    return parsed


def _import_schedule_csv_if_empty():
    _ensure_schedule_games_table()
    existing = _db.query_one("SELECT COUNT(*) AS count FROM schedule_games")
    if existing and existing["count"] > 0:
        return 0

    imported = 0
    for game in _read_schedule_csv_rows():
        _db.execute(
            "INSERT INTO schedule_games (week, home_team, away_team, status) VALUES (?, ?, ?, 'pending')",
            [game["week"], game["home_team"], game["away_team"]]
        )
        imported += 1

    if imported and not _get_site_setting("current_week"):
        _set_site_setting("current_week", "Round 1")
    return imported


def _get_schedule_games():
    _ensure_schedule_games_table()
    _import_schedule_csv_if_empty()
    rows = [dict(row) for row in _db.query("SELECT id, week, home_team, away_team, status FROM schedule_games")]
    completed_matches = _db.query("""
        SELECT
            m.id, m.stage, ht.name AS home_team, at.name AS away_team
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.status = 'completed'
    """)
    match_lookup = {
        (row["stage"], row["home_team"], row["away_team"]): row["id"]
        for row in completed_matches
    }
    for row in rows:
        row["match_id"] = match_lookup.get((row["week"], row["home_team"], row["away_team"]))
    return sorted(rows, key=lambda row: (_week_number(row["week"]), row["id"]))


def _group_schedule_games(games):
    grouped = {}
    for game in games:
        grouped.setdefault(game["week"], []).append(game)
    return grouped


def _ensure_announcements_table():
    _db.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            message     TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            order_index INTEGER NOT NULL DEFAULT 0
        )
    """)
    columns = _db.query("PRAGMA table_info(announcements)")
    col_names = {c["name"] for c in columns}
    if "order_index" not in col_names:
        _db.execute("ALTER TABLE announcements ADD COLUMN order_index INTEGER NOT NULL DEFAULT 0")


def _ensure_banner_announcements_table():
    _db.execute("""
        CREATE TABLE IF NOT EXISTS banner_announcements (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            message    TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)


def _get_banner_settings():
    _ensure_site_settings_table()
    rows = _db.query(
        "SELECT key, value FROM site_settings WHERE key IN ('banner_speed', 'banner_autoscroll')"
    )
    settings = dict(BANNER_DEFAULTS)
    for row in rows:
        settings[row["key"]] = row["value"]
    return settings

# ── CONTEXT PROCESSOR ────────────────────────────────────────
@app.context_processor
def inject_globals():
    _ensure_announcements_table()
    _ensure_banner_announcements_table()
    announcements = _db.query(
        "SELECT id, message, created_at, order_index "
        "FROM announcements ORDER BY order_index ASC, id DESC"
    )
    banner_announcements = _db.query(
        "SELECT id, message, created_at FROM banner_announcements ORDER BY id DESC"
    )
    banner_settings = _get_banner_settings()
    return {
        "current_user":       get_current_user(),
        "user_is_admin":      is_admin(),
        "site_announcements": [dict(a) for a in announcements],
        "site_banner_messages": [dict(a) for a in banner_announcements],
        "banner_settings":    banner_settings,
    }

# ─────────────────────────────────────────────────────────────
# PUBLIC ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/")
def home():
    # Recent completed matches with team names joined
    recent = _db.query("""
        SELECT
            m.id, m.home_score, m.away_score, m.date, m.stage, m.status,
            ht.name  AS home, ht.logo_url AS home_logo_url,
            at.name  AS away, at.logo_url AS away_logo_url
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.status = 'completed'
        ORDER BY m.id DESC
        LIMIT 3
    """)

    upcoming = _db.query("""
        SELECT
            m.id, m.date, m.stage, m.status,
            ht.name  AS home, ht.logo_url AS home_logo_url,
            at.name  AS away, at.logo_url AS away_logo_url
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.status = 'upcoming'
        ORDER BY m.id ASC
        LIMIT 3
    """)

    top_teams = _db.query("""
        SELECT
            t.id, t.name, t.abbr, t.logo_url, t.color,
            r.wins, r.losses,
            ROUND(CAST(r.wins AS REAL) / (r.wins + r.losses), 3) AS pct,
            ROW_NUMBER() OVER (ORDER BY r.wins DESC, r.losses ASC) AS rank
        FROM teams t
        JOIN team_records r ON r.team_id = t.id
        ORDER BY r.wins DESC, r.losses ASC
        LIMIT 3
    """)

    return render_template("home.html",
        recent=[dict(r) for r in recent],
        upcoming=[dict(u) for u in upcoming],
        top_teams=[dict(t) for t in top_teams],
    )


@app.route("/standings")
def standings():
    rows = _db.query("""
        SELECT
            t.id, t.name, t.city, t.abbr, t.logo_url, t.color,
            r.wins, r.losses, r.points_for, r.points_against,
            (r.points_for - r.points_against)                         AS diff,
            ROUND(CAST(r.wins AS REAL) / MAX(r.wins + r.losses, 1), 3) AS pct,
            ROW_NUMBER() OVER (ORDER BY r.wins DESC, r.losses ASC)     AS rank
        FROM teams t
        JOIN team_records r ON r.team_id = t.id
        ORDER BY r.wins DESC, r.losses ASC
    """)
    return render_template("standings.html", standings=[dict(r) for r in rows])


@app.route("/matches")
def matches():
    completed = _db.query("""
        SELECT
            m.id, m.home_score, m.away_score, m.date, m.stage, m.status,
            ht.name AS home, ht.logo_url AS home_logo_url,
            at.name AS away, at.logo_url AS away_logo_url
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.status = 'completed'
        ORDER BY m.id DESC
    """)
    return render_template("matches.html", completed=[dict(r) for r in completed])


@app.route("/matches/<int:match_id>")
def match_detail(match_id):
    match = _db.query_one("""
        SELECT
            m.id, m.home_team_id, m.away_team_id,
            m.home_score, m.away_score, m.date, m.stage, m.status,
            ht.name AS home, ht.abbr AS home_abbr, ht.logo_url AS home_logo_url,
            at.name AS away, at.abbr AS away_abbr, at.logo_url AS away_logo_url
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.id = ? AND m.status = 'completed'
    """, [match_id])
    if not match:
        abort(404)

    stat_rows = _db.query("""
        SELECT
            s.team_id, s.player_id, s.walkon_name, s.is_walkon,
            p.name AS player_name,
            s.pts, s.fgm, s.fga, s.three_pm, s.three_pa,
            s.ftm, s.fta, s.ast, s.reb, s.stl, s.blk,
            s.tov, s.fls, s.plus_minus
        FROM player_game_stats s
        LEFT JOIN players p ON p.id = s.player_id
        WHERE s.match_id = ?
        ORDER BY s.is_walkon ASC, s.pts DESC, p.name ASC, s.walkon_name ASC
    """, [match_id])

    stat_fields = [
        "pts", "fgm", "fga", "three_pm", "three_pa", "ftm", "fta",
        "ast", "reb", "stl", "blk", "tov", "fls", "plus_minus",
    ]
    home_stats = []
    away_stats = []
    home_totals = {field: 0 for field in stat_fields}
    away_totals = {field: 0 for field in stat_fields}

    for row in stat_rows:
        row_dict = dict(row)
        target_rows = home_stats if row["team_id"] == match["home_team_id"] else away_stats
        target_totals = home_totals if row["team_id"] == match["home_team_id"] else away_totals
        target_rows.append(row_dict)
        for field in stat_fields:
            target_totals[field] += row[field] or 0

    return render_template(
        "match_detail.html",
        match=dict(match),
        home_stats=home_stats,
        away_stats=away_stats,
        home_totals=home_totals,
        away_totals=away_totals,
    )


@app.route("/schedule")
def schedule():
    games = _get_schedule_games()
    current_week = _get_site_setting("current_week", "Round 1")
    return render_template(
        "schedule.html",
        schedule_by_week=_group_schedule_games(games),
        current_week=current_week,
        current_week_deadline=_get_site_setting("current_week_deadline", ""),
    )


@app.route("/stages/<path:stage_name>")
def stage_detail(stage_name):
    matches_by_stage = _db.query("""
        SELECT
            m.id, m.home_score, m.away_score, m.date, m.stage, m.status,
            ht.name AS home, ht.logo_url AS home_logo_url,
            at.name AS away, at.logo_url AS away_logo_url
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.stage = ?
        ORDER BY m.id ASC
    """, [stage_name])
    if not matches_by_stage:
        abort(404)
    return render_template("stage_detail.html", stage_name=stage_name, matches=[dict(m) for m in matches_by_stage])


@app.route("/teams")
def teams():
    rows = _db.query("""
        SELECT
            t.id, t.name, t.city, t.abbr, t.logo_url, t.color,
            r.wins, r.losses,
            ROUND(CAST(r.wins AS REAL) / MAX(r.wins + r.losses, 1), 3) AS pct
        FROM teams t
        JOIN team_records r ON r.team_id = t.id
        ORDER BY t.name
    """)
    # Attach roster to each team
    team_list = []
    for row in rows:
        t = dict(row)
        roster = _db.query(
            "SELECT id, name, position FROM players WHERE team_id = ? ORDER BY position, name",
            [t["id"]]
        )
        t["roster"] = [dict(p) for p in roster]
        team_list.append(t)

    return render_template("teams.html", teams=team_list)


@app.route("/teams/<int:team_id>")
def team_detail(team_id):
    team = _db.query_one("""
        SELECT
            t.id, t.name, t.city, t.abbr, t.logo_url, t.color,
            r.wins, r.losses, r.points_for, r.points_against,
            (r.points_for - r.points_against) AS diff,
            ROUND(CAST(r.wins AS REAL) / MAX(r.wins + r.losses, 1), 3) AS pct
        FROM teams t
        JOIN team_records r ON r.team_id = t.id
        WHERE t.id = ?
    """, [team_id])

    if not team:
        abort(404)

    roster = _db.query("""
        SELECT
            p.id, p.name, p.position,
            COALESCE(ROUND(AVG(s.pts), 1), 0) AS ppg,
            COALESCE(ROUND(AVG(s.ast), 1), 0) AS apg,
            COALESCE(ROUND(AVG(s.reb), 1), 0) AS rpg
        FROM players p
        LEFT JOIN player_game_stats s ON s.player_id = p.id AND s.is_walkon = 0
        WHERE p.team_id = ?
        GROUP BY p.id
        ORDER BY p.position, p.name
    """, [team_id])

    team_matches = _db.query("""
        SELECT
            m.id, m.home_score, m.away_score, m.date, m.stage, m.status,
            ht.name AS home, ht.id AS home_id, ht.logo_url AS home_logo_url,
            at.name AS away, at.id AS away_id, at.logo_url AS away_logo_url
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.home_team_id = ? OR m.away_team_id = ?
        ORDER BY m.id DESC
    """, [team_id, team_id])

    return render_template("team_detail.html",
        team=dict(team),
        roster=[dict(p) for p in roster],
        matches=[dict(m) for m in team_matches],
    )


@app.route("/players/<int:player_id>")
def player_detail(player_id):
    player = _db.query_one("""
        SELECT
            p.id, p.name, p.position,
            t.id AS team_id, t.name AS team_name, t.abbr AS team_abbr,
            t.color AS team_color, t.logo_url AS team_logo_url
        FROM players p
        JOIN teams t ON t.id = p.team_id
        WHERE p.id = ?
    """, [player_id])

    if not player:
        abort(404)

    season_totals = _db.query_one("""
        SELECT
            COUNT(s.id) AS games_played,
            COALESCE(SUM(s.pts), 0) AS pts,
            COALESCE(SUM(s.fgm), 0) AS fgm,
            COALESCE(SUM(s.fga), 0) AS fga,
            COALESCE(SUM(s.three_pm), 0) AS three_pm,
            COALESCE(SUM(s.three_pa), 0) AS three_pa,
            COALESCE(SUM(s.ftm), 0) AS ftm,
            COALESCE(SUM(s.fta), 0) AS fta,
            COALESCE(SUM(s.ast), 0) AS ast,
            COALESCE(SUM(s.reb), 0) AS reb,
            COALESCE(SUM(s.stl), 0) AS stl,
            COALESCE(SUM(s.blk), 0) AS blk,
            COALESCE(SUM(s.tov), 0) AS tov,
            COALESCE(SUM(s.fls), 0) AS fls,
            COALESCE(SUM(s.plus_minus), 0) AS plus_minus
        FROM player_game_stats s
        WHERE s.player_id = ? AND s.is_walkon = 0
    """, [player_id])

    averages = _db.query_one("""
        SELECT
            COUNT(s.id) AS games_played,
            COALESCE(ROUND(AVG(s.pts), 1), 0) AS ppg,
            COALESCE(ROUND(AVG(s.ast), 1), 0) AS apg,
            COALESCE(ROUND(AVG(s.reb), 1), 0) AS rpg,
            COALESCE(ROUND(AVG(s.stl), 1), 0) AS spg,
            COALESCE(ROUND(AVG(s.blk), 1), 0) AS bpg
        FROM player_game_stats s
        WHERE s.player_id = ? AND s.is_walkon = 0
    """, [player_id])

    game_log = _db.query("""
        SELECT
            m.id AS match_id,
            m.date,
            m.stage,
            ht.name AS home_team,
            at.name AS away_team,
            m.home_score,
            m.away_score,
            s.pts,
            s.fgm,
            s.fga,
            s.three_pm,
            s.three_pa,
            s.ftm,
            s.fta,
            s.ast,
            s.reb,
            s.stl,
            s.blk,
            s.tov,
            s.fls,
            s.plus_minus,
            s.is_walkon,
            CASE
                WHEN s.is_walkon = 1 THEN s.walkon_name
                ELSE p.name
            END AS display_name
        FROM player_game_stats s
        LEFT JOIN players p ON p.id = s.player_id
        JOIN matches m ON m.id = s.match_id
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE s.player_id = ? OR (s.is_walkon = 1 AND s.team_id = ?)
        ORDER BY m.id DESC
    """, [player_id, player["team_id"]])

    return render_template(
        "player_detail.html",
        player=dict(player),
        season_totals=dict(season_totals) if season_totals else {},
        averages=dict(averages) if averages else {},
        game_log=[dict(row) for row in game_log],
    )


@app.route("/statistics")
def statistics():
    # Shared base CTE for all leaderboards — avoids repeating the JOIN
    BASE = """
        FROM players p
        JOIN teams t ON t.id = p.team_id
        JOIN player_game_stats s ON s.player_id = p.id
        WHERE s.is_walkon = 0
        GROUP BY p.id
        HAVING COUNT(s.id) >= 1
    """

    top_scorers = _db.query(f"""
        SELECT
            p.id, p.name, p.position,
            t.name AS team, t.abbr AS team_abbr,
            COUNT(s.id)                               AS gp,
            ROUND(AVG(s.pts), 1)                      AS ppg,
            ROUND(AVG(s.ast), 1)                      AS apg,
            ROUND(AVG(s.reb), 1)                      AS rpg,
            ROUND(AVG(s.stl), 1)                      AS spg,
            ROUND(AVG(s.blk), 1)                      AS bpg,
            ROUND(
                CASE WHEN SUM(s.fga) > 0
                     THEN 100.0 * SUM(s.fgm) / SUM(s.fga)
                     ELSE 0 END, 1)                   AS fg_pct
        {BASE}
        ORDER BY ppg DESC LIMIT 8
    """)

    top_assists = _db.query(f"""
        SELECT
            p.id, p.name, p.position,
            t.name AS team, t.abbr AS team_abbr,
            COUNT(s.id)          AS gp,
            ROUND(AVG(s.pts), 1) AS ppg,
            ROUND(AVG(s.ast), 1) AS apg,
            ROUND(AVG(s.reb), 1) AS rpg
        {BASE}
        ORDER BY apg DESC LIMIT 8
    """)

    top_rebounds = _db.query(f"""
        SELECT
            p.id, p.name, p.position,
            t.name AS team, t.abbr AS team_abbr,
            COUNT(s.id)          AS gp,
            ROUND(AVG(s.reb), 1) AS rpg,
            ROUND(AVG(s.blk), 1) AS bpg,
            ROUND(AVG(s.pts), 1) AS ppg
        {BASE}
        ORDER BY rpg DESC LIMIT 8
    """)

    # MVP = pts*1.0 + ast*1.5 + reb*1.2 + stl*2.0 + blk*2.0
    mvp_race = _db.query(f"""
        SELECT
            p.id, p.name, p.position,
            t.name AS team, t.abbr AS team_abbr,
            COUNT(s.id)          AS gp,
            ROUND(AVG(s.pts), 1) AS ppg,
            ROUND(AVG(s.ast), 1) AS apg,
            ROUND(AVG(s.reb), 1) AS rpg,
            ROUND(AVG(s.stl), 1) AS spg,
            ROUND(AVG(s.blk), 1) AS bpg,
            ROUND(
                AVG(s.pts) * 1.0 +
                AVG(s.ast) * 1.5 +
                AVG(s.reb) * 1.2 +
                AVG(s.stl) * 2.0 +
                AVG(s.blk) * 2.0, 1) AS mvp_score
        {BASE}
        ORDER BY mvp_score DESC LIMIT 6
    """)

    return render_template("statistics.html",
        top_scorers=[dict(r) for r in top_scorers],
        top_assists=[dict(r) for r in top_assists],
        top_rebounds=[dict(r) for r in top_rebounds],
        mvp_race=[dict(r) for r in mvp_race],
    )


# ─────────────────────────────────────────────────────────────
# DISCORD AUTH ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/login")
def login():
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    params = {
        "client_id":     DISCORD_CLIENT_ID,
        "redirect_uri":  DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope":         "identify",
        "state":         state,
    }
    return redirect(f"{DISCORD_AUTH_URL}?{urlencode(params)}")


@app.route("/callback")
def callback():
    error = request.args.get("error")
    if error:
        flash(f"Discord login failed: {error}", "error")
        return redirect(url_for("home"))

    state = request.args.get("state")
    if state != session.pop("oauth_state", None):
        flash("Invalid OAuth state. Please try again.", "error")
        return redirect(url_for("home"))

    code = request.args.get("code")
    if not code:
        flash("No authorization code returned from Discord.", "error")
        return redirect(url_for("home"))

    token_res = requests.post(DISCORD_TOKEN_URL, data={
        "client_id":     DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  DISCORD_REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})

    if token_res.status_code != 200:
        flash("Failed to retrieve access token from Discord.", "error")
        return redirect(url_for("home"))

    access_token = token_res.json().get("access_token")

    user_res = requests.get(f"{DISCORD_API_BASE}/users/@me", headers={
        "Authorization": f"Bearer {access_token}"
    })
    if user_res.status_code != 200:
        flash("Failed to fetch user info from Discord.", "error")
        return redirect(url_for("home"))

    d = user_res.json()
    avatar_hash = d.get("avatar")
    avatar_url = (
        f"https://cdn.discordapp.com/avatars/{d['id']}/{avatar_hash}.png"
        if avatar_hash
        else f"https://cdn.discordapp.com/embed/avatars/{int(d.get('discriminator') or 0) % 5}.png"
    )
    session["user"] = {"id": d["id"], "username": d["username"], "avatar": avatar_url}
    flash(f"Welcome, {d['username']}!", "success")
    return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("You've been logged out.", "success")
    return redirect(url_for("home"))


# ─────────────────────────────────────────────────────────────
# ADMIN ROUTES
# ─────────────────────────────────────────────────────────────

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    if request.method == "POST":
        action = request.form.get("action")

        # ── A: Announcements ──────────────────────────────────
        if action == "add_announcement":
            msg = request.form.get("message", "").strip()
            if msg:
                _ensure_announcements_table()
                max_order = _db.query_one(
                    "SELECT COALESCE(MAX(order_index), 0) AS max_order FROM announcements"
                )
                _db.execute(
                    "INSERT INTO announcements (message, created_at, order_index) VALUES (?, ?, ?)",
                    [msg, datetime.now().strftime("%b %d, %Y"), int(max_order["max_order"]) + 1]
                )
                flash("Announcement posted.", "success")
            else:
                flash("Announcement message cannot be empty.", "error")

        elif action == "delete_announcement":
            aid = request.form.get("announcement_id", "")
            if aid.isdigit():
                _ensure_announcements_table()
                _db.execute("DELETE FROM announcements WHERE id = ?", [int(aid)])
                flash("Announcement deleted.", "success")

        elif action == "add_banner_announcement":
            msg = request.form.get("message", "").strip()
            if msg:
                _ensure_banner_announcements_table()
                _db.execute(
                    "INSERT INTO banner_announcements (message, created_at) VALUES (?, ?)",
                    [msg, datetime.now().strftime("%b %d, %Y")]
                )
                flash("Banner message added.", "success")
            else:
                flash("Banner message cannot be empty.", "error")

        elif action == "delete_banner_announcement":
            bid = request.form.get("banner_announcement_id", "").strip()
            if bid.isdigit():
                _ensure_banner_announcements_table()
                _db.execute("DELETE FROM banner_announcements WHERE id = ?", [int(bid)])
                flash("Banner message deleted.", "success")

        elif action == "save_banner_settings":
            autoscroll = "true" if request.form.get("banner_autoscroll") == "on" else "false"
            speed_raw = request.form.get("banner_speed", "").strip()
            try:
                speed = max(2, min(30, int(speed_raw)))
            except ValueError:
                speed = int(BANNER_DEFAULTS["banner_speed"])

            _ensure_site_settings_table()
            _db.execute(
                "INSERT INTO site_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ["banner_autoscroll", autoscroll]
            )
            _db.execute(
                "INSERT INTO site_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ["banner_speed", str(speed)]
            )
            flash("Banner settings updated.", "success")

        elif action == "mark_schedule_completed":
            game_id = request.form.get("schedule_game_id", "").strip()
            if game_id.isdigit():
                _ensure_schedule_games_table()
                _db.execute("UPDATE schedule_games SET status = 'completed' WHERE id = ?", [int(game_id)])
                flash("Schedule game marked completed.", "success")
            else:
                flash("Select a schedule game first.", "error")

        elif action == "set_current_week":
            current_week = _normalize_week(request.form.get("current_week", ""))
            deadline = request.form.get("current_week_deadline", "").strip()
            if current_week:
                _set_site_setting("current_week", current_week)
                _set_site_setting("current_week_deadline", deadline)
                flash("Current schedule round updated.", "success")
            else:
                flash("Select a current round.", "error")

        # ── B: Full Match + Box-Score Entry ──────────────────
        elif action == "add_match":
            home_id = request.form.get("home_team_id", "").strip()
            away_id = request.form.get("away_team_id", "").strip()
            hs      = request.form.get("home_score",   "").strip()
            as_     = request.form.get("away_score",   "").strip()
            stage   = request.form.get("stage", "Admin Entry").strip()
            date_   = request.form.get("date",  datetime.now().strftime("%b %d, %Y")).strip()

            if not (home_id.isdigit() and away_id.isdigit()
                    and hs.isdigit() and as_.isdigit()
                    and home_id != away_id):
                flash("Fill in all match fields correctly.", "error")
                return redirect(url_for("admin"))

            home_id, away_id = int(home_id), int(away_id)
            hs, as_ = int(hs), int(as_)

            cur = _db.execute("""
                INSERT INTO matches
                    (home_team_id, away_team_id, home_score, away_score, status, date, stage)
                VALUES (?, ?, ?, ?, 'completed', ?, ?)
            """, [home_id, away_id, hs, as_, date_, stage])
            match_id = cur.lastrowid
            _update_team_record(home_id, away_id, hs, as_)

            errors = []
            inserted = 0
            for side, team_id in (("home", home_id), ("away", away_id)):
                prefix = f"{side}_player"
                indices = set()
                for key in request.form:
                    if key.startswith(f"{prefix}[") and "][" in key:
                        idx = key.split("[")[1].split("]")[0]
                        if idx.isdigit():
                            indices.add(int(idx))
                for idx in sorted(indices):
                    pid_raw = request.form.get(f"{prefix}[{idx}][player_id]", "").strip()
                    walkon_name = request.form.get(f"{prefix}[{idx}][walkon_name]", "").strip()
                    is_walkon = pid_raw == "__walkon__"

                    if is_walkon:
                        if not walkon_name:
                            continue
                        pid = None
                    elif pid_raw.isdigit():
                        pid = int(pid_raw)
                    else:
                        continue

                    if not is_walkon:
                        owner = _db.query_one("SELECT team_id FROM players WHERE id = ?", [pid])
                        if not owner or owner["team_id"] != team_id:
                            errors.append(f"Player {pid} does not belong to team {team_id}.")
                            continue
                    def _int(field, _prefix=prefix, _idx=idx, default=0):
                        v = request.form.get(f"{_prefix}[{_idx}][{field}]", "").strip()
                        try: return int(v)
                        except: return default
                    try:
                        _db.execute("""
                            INSERT OR IGNORE INTO player_game_stats
                                (player_id, match_id, team_id, is_walkon, walkon_name,
                                 pts, fgm, fga, three_pm, three_pa, ftm, fta,
                                 ast, stl, blk, reb, tov, fls, plus_minus)
                            VALUES (?,?,?,?,?, ?,?,?,?,?,?,?, ?,?,?,?,?,?,?)
                        """, [pid, match_id, team_id, 1 if is_walkon else 0, walkon_name if is_walkon else None,
                              _int("pts"), _int("fgm"), _int("fga"),
                              _int("three_pm"), _int("three_pa"),
                              _int("ftm"), _int("fta"),
                              _int("ast"), _int("stl"), _int("blk"),
                              _int("reb"), _int("tov"), _int("fls"),
                              _int("plus_minus")])
                        inserted += 1
                    except Exception as e:
                        errors.append(str(e))

            if errors:
                flash(f"Match saved but {len(errors)} stat row(s) had errors: {'; '.join(errors[:3])}", "error")
            else:
                flash(f"Match saved (ID {match_id}) with {inserted} player stat lines.", "success")

        # ── C: Player Transfer ────────────────────────────────
        elif action == "transfer_player":
            player_id = request.form.get("player_id", "").strip()
            new_team  = request.form.get("new_team_id", "").strip()
            if player_id.isdigit() and new_team.isdigit():
                player = _db.query_one("SELECT name FROM players WHERE id = ?", [int(player_id)])
                team   = _db.query_one("SELECT name FROM teams   WHERE id = ?", [int(new_team)])
                if player and team:
                    _db.execute("UPDATE players SET team_id = ? WHERE id = ?",
                                [int(new_team), int(player_id)])
                    flash(f"{player['name']} transferred to {team['name']}.", "success")
                else:
                    flash("Invalid player or team.", "error")
            else:
                flash("Invalid selection.", "error")

        elif action == "add_player":
            team_id = request.form.get("team_id", "").strip()
            name = request.form.get("name", "").strip()
            position = request.form.get("position", "").strip()
            valid_positions = {"PG", "SG", "SF", "PF", "C"}
            if team_id.isdigit() and name and position in valid_positions:
                _db.execute(
                    "INSERT INTO players (name, team_id, position) VALUES (?, ?, ?)",
                    [name, int(team_id), position]
                )
                flash(f"{name} added to roster.", "success")
            else:
                flash("Invalid roster add input.", "error")

        elif action == "remove_player":
            player_id = request.form.get("player_id", "").strip()
            if player_id.isdigit():
                player = _db.query_one("SELECT name FROM players WHERE id = ?", [int(player_id)])
                if player:
                    _db.execute("DELETE FROM players WHERE id = ?", [int(player_id)])
                    flash(f"{player['name']} removed from roster.", "success")
                else:
                    flash("Player not found.", "error")
            else:
                flash("Invalid player selection.", "error")

        elif action == "create_team":
            name = request.form.get("team_name", "").strip()
            city = request.form.get("city", "").strip()
            abbr = request.form.get("abbreviation", "").strip().upper()
            logo_url = request.form.get("logo_url", "").strip() or url_for("static", filename="img/team-logo-fallback.svg")
            color = request.form.get("primary_color", "").strip() or "#ff7a00"
            roster_text = request.form.get("initial_roster", "").strip()

            if not (name and city and abbr):
                flash("Team name, city, and abbreviation are required.", "error")
                return redirect(url_for("admin"))

            if not color.startswith("#"):
                color = f"#{color}"
            if len(color) not in {4, 7}:
                color = "#ff7a00"

            try:
                cur = _db.execute(
                    "INSERT INTO teams (name, city, abbr, color, logo, logo_url) VALUES (?, ?, ?, ?, ?, ?)",
                    [name, city, abbr[:5], color, "", logo_url]
                )
                team_id = int(cur.lastrowid)
                _db.execute(
                    "INSERT INTO team_records (team_id, wins, losses, points_for, points_against) VALUES (?, 0, 0, 0, 0)",
                    [team_id]
                )
            except Exception as exc:
                flash(f"Could not create team: {exc}", "error")
                return redirect(url_for("admin"))

            created_players = 0
            valid_positions = {"PG", "SG", "SF", "PF", "C"}
            if roster_text:
                for raw_line in roster_text.splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    parts = [p.strip() for p in line.split(",")]
                    pname = parts[0] if parts else ""
                    ppos = (parts[1].upper() if len(parts) > 1 else "SG")
                    if not pname:
                        continue
                    if ppos not in valid_positions:
                        ppos = "SG"
                    _db.execute(
                        "INSERT INTO players (name, team_id, position) VALUES (?, ?, ?)",
                        [pname, team_id, ppos]
                    )
                    created_players += 1

            flash(
                f"Team {name} created successfully with {created_players} initial player(s).",
                "success"
            )

        return redirect(url_for("admin"))

    # ── GET ───────────────────────────────────────────────────
    _ensure_announcements_table()
    announcements = _db.query(
        "SELECT id, message, created_at, order_index "
        "FROM announcements ORDER BY order_index ASC, id DESC"
    )
    _ensure_banner_announcements_table()
    banner_announcements = _db.query(
        "SELECT id, message, created_at FROM banner_announcements ORDER BY id DESC"
    )
    all_teams = _db.query("SELECT id, name, abbr, color, logo_url FROM teams ORDER BY name")
    all_players = _db.query("""
        SELECT p.id, p.name, p.position, p.team_id,
               t.name AS team, t.abbr AS team_abbr
        FROM players p
        JOIN teams t ON t.id = p.team_id
        ORDER BY t.name, p.position, p.name
    """)
    recent_matches = _db.query("""
        SELECT m.id, m.home_score, m.away_score, m.date, m.stage,
               ht.name AS home, at.name AS away
        FROM matches m
        JOIN teams ht ON ht.id = m.home_team_id
        JOIN teams at ON at.id = m.away_team_id
        WHERE m.status = 'completed'
        ORDER BY m.id DESC LIMIT 5
    """)

    import json
    players_by_team = {}
    for p in all_players:
        tid = str(p["team_id"])
        players_by_team.setdefault(tid, []).append({
            "id": p["id"], "name": p["name"], "position": p["position"]
        })
    banner_settings = _get_banner_settings()
    schedule_games = _get_schedule_games()
    schedule_weeks = sorted({game["week"] for game in schedule_games}, key=_week_number)

    return render_template("admin.html",
        announcements=[dict(a) for a in announcements],
        banner_announcements=[dict(a) for a in banner_announcements],
        recent_matches=[dict(m) for m in recent_matches],
        players=[dict(p) for p in all_players],
        teams=[dict(t) for t in all_teams],
        players_by_team_json=json.dumps(players_by_team),
        banner_settings=banner_settings,
        schedule_games=schedule_games,
        schedule_weeks=schedule_weeks,
        current_week=_get_site_setting("current_week", "Round 1"),
        current_week_deadline=_get_site_setting("current_week_deadline", ""),
    )


def _update_team_record(home_id: int, away_id: int, home_score: int, away_score: int):
    """Increment wins/losses and point totals for both teams after a result is saved."""
    if home_score > away_score:
        # home wins
        _db.execute("""
            UPDATE team_records
            SET wins           = wins + 1,
                points_for     = points_for     + ?,
                points_against = points_against + ?
            WHERE team_id = ?
        """, [home_score, away_score, home_id])
        _db.execute("""
            UPDATE team_records
            SET losses         = losses + 1,
                points_for     = points_for     + ?,
                points_against = points_against + ?
            WHERE team_id = ?
        """, [away_score, home_score, away_id])
    else:
        # away wins (or tie treated as away win edge case)
        _db.execute("""
            UPDATE team_records
            SET losses         = losses + 1,
                points_for     = points_for     + ?,
                points_against = points_against + ?
            WHERE team_id = ?
        """, [home_score, away_score, home_id])
        _db.execute("""
            UPDATE team_records
            SET wins           = wins + 1,
                points_for     = points_for     + ?,
                points_against = points_against + ?
            WHERE team_id = ?
        """, [away_score, home_score, away_id])


# ─────────────────────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────────────────────

@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host='0.0.0.0')

# TODO
"""
ADMIN PANEL:
add game stats feature (plus button dropdowns i think)
    - ad

"""

import os
import secrets
import requests
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, session, redirect,
    url_for, request, flash, abort
)
from dotenv import load_dotenv

app = Flask(__name__)

# ── SECRET KEY ────────────────────────────────────────────
# In production set this via environment variable, never hardcode
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

# ── DISCORD OAUTH2 CONFIG ─────────────────────────────────
DISCORD_CLIENT_ID     = os.environ.get("DISCORD_CLIENT_ID",     "YOUR_CLIENT_ID_HERE")
DISCORD_CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE")
DISCORD_REDIRECT_URI  = os.environ.get("DISCORD_REDIRECT_URI",  "http://localhost:5000/callback")
DISCORD_API_BASE      = "https://discord.com/api/v10"
DISCORD_AUTH_URL      = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN_URL     = "https://discord.com/api/oauth2/token"

# ── ADMIN CONFIG ──────────────────────────────────────────
# Replace with real Discord user IDs (strings)
ADMIN_IDS = {
    "123456789012345678",   # dummy ids (1 and 2)
    "987654321098765432",   
    "500424973383499776",   # me (random)
    "909678248529649694"    # LRT
}

# ── MOCK STORAGE (in-memory, resets on restart) ───────────
ANNOUNCEMENTS = [
    {"id": 1, "message": "Season 4 playoffs begin May 2nd — don't miss it!", "created": "Apr 10, 2025"},
]
_announcement_counter = 2   # next announcement id

# ── AUTH HELPERS ──────────────────────────────────────────
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

# ── CONTEXT PROCESSOR: inject user into all templates ─────
@app.context_processor
def inject_user():
    return {
        "current_user": get_current_user(),
        "user_is_admin": is_admin(),
        "site_announcements": ANNOUNCEMENTS,
    }

TEAMS = [
    {
        "id": 1,
        "name": "Neon Wolves",
        "abbr": "NW",
        "city": "New York",
        "color": "#00f0ff",
        "logo": "🐺",
        "wins": 18,
        "losses": 4,
        "points_for": 2340,
        "points_against": 1980,
        "roster": [
            {"name": "xShadowKing", "position": "PG", "rating": 98},
            {"name": "BlazeFury99", "position": "SG", "rating": 95},
            {"name": "VoidRunner", "position": "SF", "rating": 92},
            {"name": "TitanGrip", "position": "PF", "rating": 90},
            {"name": "CenterPulse", "position": "C", "rating": 88},
        ],
    },
    {
        "id": 2,
        "name": "Apex Surge",
        "abbr": "AS",
        "city": "Los Angeles",
        "color": "#ff3c3c",
        "logo": "⚡",
        "wins": 16,
        "losses": 6,
        "points_for": 2210,
        "points_against": 2050,
        "roster": [
            {"name": "ApexPred", "position": "PG", "rating": 96},
            {"name": "LightningRod7", "position": "SG", "rating": 94},
            {"name": "StormBreaker", "position": "SF", "rating": 93},
            {"name": "IronWall22", "position": "PF", "rating": 89},
            {"name": "DoomPost", "position": "C", "rating": 87},
        ],
    },
    {
        "id": 3,
        "name": "Ghost Protocol",
        "abbr": "GP",
        "city": "Chicago",
        "color": "#a855f7",
        "logo": "👻",
        "wins": 14,
        "losses": 8,
        "points_for": 2100,
        "points_against": 2000,
        "roster": [
            {"name": "PhantomStep", "position": "PG", "rating": 93},
            {"name": "GhostFlicker", "position": "SG", "rating": 91},
            {"name": "SilentBlade", "position": "SF", "rating": 90},
            {"name": "EchoFist", "position": "PF", "rating": 88},
            {"name": "VoidAnchor", "position": "C", "rating": 85},
        ],
    },
    {
        "id": 4,
        "name": "Iron Circuit",
        "abbr": "IC",
        "city": "Houston",
        "color": "#f97316",
        "logo": "⚙️",
        "wins": 13,
        "losses": 9,
        "points_for": 2080,
        "points_against": 2090,
        "roster": [
            {"name": "CyberCore", "position": "PG", "rating": 92},
            {"name": "WireFrame", "position": "SG", "rating": 90},
            {"name": "GlitchShot", "position": "SF", "rating": 88},
            {"name": "SteelPlate", "position": "PF", "rating": 87},
            {"name": "PixelTower", "position": "C", "rating": 86},
        ],
    },
    {
        "id": 5,
        "name": "Solar Wraith",
        "abbr": "SW",
        "city": "Miami",
        "color": "#eab308",
        "logo": "☀️",
        "wins": 11,
        "losses": 11,
        "points_for": 1990,
        "points_against": 2010,
        "roster": [
            {"name": "SunBurner", "position": "PG", "rating": 91},
            {"name": "HeatMirage", "position": "SG", "rating": 89},
            {"name": "ScorchWing", "position": "SF", "rating": 87},
            {"name": "FlareKnuckle", "position": "PF", "rating": 86},
            {"name": "InfernoPost", "position": "C", "rating": 84},
        ],
    },
    {
        "id": 6,
        "name": "Cryo Strike",
        "abbr": "CS",
        "city": "Seattle",
        "color": "#06b6d4",
        "logo": "❄️",
        "wins": 9,
        "losses": 13,
        "points_for": 1870,
        "points_against": 2050,
        "roster": [
            {"name": "FrostByte", "position": "PG", "rating": 89},
            {"name": "IceDagger", "position": "SG", "rating": 87},
            {"name": "BlizzardWing", "position": "SF", "rating": 86},
            {"name": "GlacierFist", "position": "PF", "rating": 84},
            {"name": "ArcticPillar", "position": "C", "rating": 83},
        ],
    },
    {
        "id": 7,
        "name": "Rogue Signal",
        "abbr": "RS",
        "city": "Atlanta",
        "color": "#22c55e",
        "logo": "📡",
        "wins": 7,
        "losses": 15,
        "points_for": 1760,
        "points_against": 2120,
        "roster": [
            {"name": "StaticNoise", "position": "PG", "rating": 87},
            {"name": "FreqJammer", "position": "SG", "rating": 85},
            {"name": "WaveHacker", "position": "SF", "rating": 84},
            {"name": "SignalBreak", "position": "PF", "rating": 82},
            {"name": "DeadZone", "position": "C", "rating": 81},
        ],
    },
    {
        "id": 8,
        "name": "Dark Matter",
        "abbr": "DM",
        "city": "Phoenix",
        "color": "#ec4899",
        "logo": "🌑",
        "wins": 4,
        "losses": 18,
        "points_for": 1630,
        "points_against": 2270,
        "roster": [
            {"name": "VoidPulse", "position": "PG", "rating": 84},
            {"name": "DarkSpin", "position": "SG", "rating": 82},
            {"name": "NullShift", "position": "SF", "rating": 80},
            {"name": "AbyssCharge", "position": "PF", "rating": 79},
            {"name": "EventHorizon", "position": "C", "rating": 78},
        ],
    },
]

MATCHES = [
    # Completed
    {"id": 1, "home": "Neon Wolves", "away": "Apex Surge", "home_score": 112, "away_score": 98, "status": "completed", "date": "Apr 10, 2025", "stage": "Week 12"},
    {"id": 2, "home": "Ghost Protocol", "away": "Iron Circuit", "home_score": 105, "away_score": 101, "status": "completed", "date": "Apr 10, 2025", "stage": "Week 12"},
    {"id": 3, "home": "Solar Wraith", "away": "Cryo Strike", "home_score": 98, "away_score": 95, "status": "completed", "date": "Apr 11, 2025", "stage": "Week 12"},
    {"id": 4, "home": "Rogue Signal", "away": "Dark Matter", "home_score": 88, "away_score": 79, "status": "completed", "date": "Apr 11, 2025", "stage": "Week 12"},
    {"id": 5, "home": "Apex Surge", "away": "Ghost Protocol", "home_score": 110, "away_score": 104, "status": "completed", "date": "Apr 7, 2025", "stage": "Week 11"},
    {"id": 6, "home": "Neon Wolves", "away": "Cryo Strike", "home_score": 121, "away_score": 88, "status": "completed", "date": "Apr 7, 2025", "stage": "Week 11"},
    # Upcoming
    {"id": 7, "home": "Neon Wolves", "away": "Ghost Protocol", "home_score": None, "away_score": None, "status": "upcoming", "date": "Apr 18, 2025", "stage": "Week 13"},
    {"id": 8, "home": "Apex Surge", "away": "Iron Circuit", "home_score": None, "away_score": None, "status": "upcoming", "date": "Apr 18, 2025", "stage": "Week 13"},
    {"id": 9, "home": "Solar Wraith", "away": "Dark Matter", "home_score": None, "away_score": None, "status": "upcoming", "date": "Apr 19, 2025", "stage": "Week 13"},
    {"id": 10, "home": "Cryo Strike", "away": "Rogue Signal", "home_score": None, "away_score": None, "status": "upcoming", "date": "Apr 19, 2025", "stage": "Week 13"},
]

STANDINGS = sorted(TEAMS, key=lambda t: (-t["wins"], t["losses"]))
for i, team in enumerate(STANDINGS):
    team["rank"] = i + 1
    team["pct"] = round(team["wins"] / (team["wins"] + team["losses"]), 3) if (team["wins"] + team["losses"]) > 0 else 0.000
    team["diff"] = team["points_for"] - team["points_against"]


@app.route("/")
def home():
    recent = [m for m in MATCHES if m["status"] == "completed"][:3]
    upcoming = [m for m in MATCHES if m["status"] == "upcoming"][:3]
    top_teams = STANDINGS[:3]
    return render_template("home.html", recent=recent, upcoming=upcoming, top_teams=top_teams)


@app.route("/standings")
def standings():
    return render_template("standings.html", standings=STANDINGS)


@app.route("/matches")
def matches():
    completed = [m for m in MATCHES if m["status"] == "completed"]
    upcoming = [m for m in MATCHES if m["status"] == "upcoming"]
    return render_template("matches.html", completed=completed, upcoming=upcoming)


@app.route("/teams")
def teams():
    return render_template("teams.html", teams=TEAMS)


@app.route("/teams/<int:team_id>")
def team_detail(team_id):
    team = next((t for t in TEAMS if t["id"] == team_id), None)
    if not team:
        return "Team not found", 404
    team_matches = [m for m in MATCHES if team["name"] in (m["home"], m["away"])]
    return render_template("team_detail.html", team=team, matches=team_matches)


PLAYERS = [
    {"name": "xShadowKing",   "team": "Neon Wolves",    "team_abbr": "NW", "pos": "PG", "gp": 22, "ppg": 34.2, "apg": 9.1, "rpg": 5.8, "spg": 2.3, "bpg": 0.4, "fg_pct": 52.1, "mvp_score": 96},
    {"name": "ApexPred",      "team": "Apex Surge",     "team_abbr": "AS", "pos": "PG", "gp": 22, "ppg": 30.7, "apg": 10.4, "rpg": 4.2, "spg": 1.9, "bpg": 0.2, "fg_pct": 49.8, "mvp_score": 91},
    {"name": "BlazeFury99",   "team": "Neon Wolves",    "team_abbr": "NW", "pos": "SG", "gp": 21, "ppg": 27.4, "apg": 5.2, "rpg": 4.1, "spg": 1.6, "bpg": 0.3, "fg_pct": 48.3, "mvp_score": 85},
    {"name": "TitanGrip",     "team": "Neon Wolves",    "team_abbr": "NW", "pos": "PF", "gp": 22, "ppg": 18.9, "apg": 3.1, "rpg": 12.7, "spg": 0.8, "bpg": 2.1, "fg_pct": 55.7, "mvp_score": 82},
    {"name": "PhantomStep",   "team": "Ghost Protocol", "team_abbr": "GP", "pos": "PG", "gp": 22, "ppg": 25.1, "apg": 11.8, "rpg": 3.9, "spg": 2.0, "bpg": 0.1, "fg_pct": 47.2, "mvp_score": 88},
    {"name": "CenterPulse",   "team": "Neon Wolves",    "team_abbr": "NW", "pos": "C",  "gp": 20, "ppg": 16.3, "apg": 2.4, "rpg": 14.5, "spg": 0.5, "bpg": 3.2, "fg_pct": 61.4, "mvp_score": 78},
    {"name": "LightningRod7", "team": "Apex Surge",     "team_abbr": "AS", "pos": "SG", "gp": 21, "ppg": 24.9, "apg": 4.8, "rpg": 3.7, "spg": 1.7, "bpg": 0.2, "fg_pct": 46.9, "mvp_score": 80},
    {"name": "SunBurner",     "team": "Solar Wraith",   "team_abbr": "SW", "pos": "PG", "gp": 22, "ppg": 22.6, "apg": 7.3, "rpg": 4.4, "spg": 1.5, "bpg": 0.3, "fg_pct": 45.1, "mvp_score": 76},
    {"name": "GhostFlicker",  "team": "Ghost Protocol", "team_abbr": "GP", "pos": "SG", "gp": 22, "ppg": 21.3, "apg": 3.9, "rpg": 3.1, "spg": 1.8, "bpg": 0.2, "fg_pct": 44.8, "mvp_score": 72},
    {"name": "CyberCore",     "team": "Iron Circuit",   "team_abbr": "IC", "pos": "PG", "gp": 22, "ppg": 20.8, "apg": 8.6, "rpg": 3.8, "spg": 1.4, "bpg": 0.1, "fg_pct": 43.2, "mvp_score": 74},
]

top_scorers  = sorted(PLAYERS, key=lambda p: -p["ppg"])
top_assists  = sorted(PLAYERS, key=lambda p: -p["apg"])
top_rebounds = sorted(PLAYERS, key=lambda p: -p["rpg"])
mvp_race     = sorted(PLAYERS, key=lambda p: -p["mvp_score"])


@app.route("/statistics")
def statistics():
    return render_template(
        "statistics.html",
        top_scorers=top_scorers[:8],
        top_assists=top_assists[:8],
        top_rebounds=top_rebounds[:8],
        mvp_race=mvp_race[:6],
    )


# ── DISCORD AUTH ROUTES ───────────────────────────────────

@app.route("/login")
def login():
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    from urllib.parse import urlencode
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
    expected_state = session.get("oauth_state")

    if not state or state != expected_state:
        print("EXPECTED STATE:", expected_state)
        print("RECEIVED STATE:", state)
        flash("Invalid OAuth state. Please try again.", "error")
        return redirect(url_for("home"))

    # only remove AFTER it passes
    session.pop("oauth_state", None)

    code = request.args.get("code")
    if not code:
        flash("No authorization code returned from Discord.", "error")
        return redirect(url_for("home"))

    token_res = requests.post(
        DISCORD_TOKEN_URL,
        data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI,
        },
        headers={
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    print("STATUS:", token_res.status_code)
    print("RESPONSE:", token_res.text)

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


# ── ADMIN ROUTES ──────────────────────────────────────────

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    global _announcement_counter

    if request.method == "POST":
        action = request.form.get("action")

        # A: Announcements
        if action == "add_announcement":
            msg = request.form.get("message", "").strip()
            if msg:
                ANNOUNCEMENTS.insert(0, {
                    "id":      _announcement_counter,
                    "message": msg,
                    "created": datetime.now().strftime("%b %d, %Y"),
                })
                _announcement_counter += 1
                flash("Announcement posted.", "success")
            else:
                flash("Announcement message cannot be empty.", "error")

        elif action == "delete_announcement":
            aid = int(request.form.get("announcement_id", -1))
            ANNOUNCEMENTS[:] = [a for a in ANNOUNCEMENTS if a["id"] != aid]
            flash("Announcement deleted.", "success")

        # B: Match Results
        elif action == "add_match":
            ht  = request.form.get("home_team", "").strip()
            at  = request.form.get("away_team", "").strip()
            hs  = request.form.get("home_score", "").strip()
            as_ = request.form.get("away_score", "").strip()
            st  = request.form.get("stage", "Admin Entry").strip()
            if ht and at and hs.isdigit() and as_.isdigit() and ht != at:
                new_id = max(m["id"] for m in MATCHES) + 1
                MATCHES.append({
                    "id": new_id, "home": ht, "away": at,
                    "home_score": int(hs), "away_score": int(as_),
                    "status": "completed",
                    "date": datetime.now().strftime("%b %d, %Y"),
                    "stage": st,
                })
                flash(f"Match added: {ht} {hs}–{as_} {at}", "success")
            else:
                flash("Fill in all match fields correctly (different teams, numeric scores).", "error")

        # C: Player Transfer
        elif action == "transfer_player":
            player_name = request.form.get("player_name", "").strip()
            new_team    = request.form.get("new_team", "").strip()
            abbr_map    = {t["name"]: t["abbr"] for t in TEAMS}
            player = next((p for p in PLAYERS if p["name"] == player_name), None)
            if player and new_team in abbr_map:
                old_team = player["team"]
                player["team"]      = new_team
                player["team_abbr"] = abbr_map[new_team]
                flash(f"{player_name} transferred from {old_team} to {new_team}.", "success")
            else:
                flash("Invalid player or team selection.", "error")

        return redirect(url_for("admin"))

    team_names = [t["name"] for t in TEAMS]
    recent_matches = [m for m in MATCHES if m["status"] == "completed"][-5:][::-1]
    return render_template(
        "admin.html",
        announcements=ANNOUNCEMENTS,
        recent_matches=recent_matches,
        players=PLAYERS,
        teams=team_names,
    )


@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403

if __name__ == "__main__":
    app.run(debug=True)

    app.secret_key = os.getenv("SECRET_KEY")

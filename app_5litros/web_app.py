"""
Flask + SocketIO web application for 5 Litros.

Routes
──────
/                         → Home page with navigation
/video/play/<index>       → Full‑screen video player
/data/play/<index>        → Data / estimation overlay
/global                   → Global AI water consumption counter
/info                     → PDF info viewer (home-only link)
/api/reload               → JSON endpoint (used by loading page polling)

Expo mode
─────────
Append ?expo=1 to any route to hide the bottom navigation bar.
The home page provides direct expo-mode links.
"""

from datetime import datetime
from pathlib import Path
import random

from flask import (Flask, jsonify, render_template, request,
                   redirect, send_from_directory, url_for)
from flask_socketio import SocketIO, emit
import json

# ── App setup ───────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = "5litros-secret-key"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

DATA_DIR = Path("./data")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _load_json(path):
    """Safely load a JSON file; returns {} on any error."""
    try:
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"  ⚠ Could not load {path}: {e}")
    return {}


def _estimates_path():
    return DATA_DIR / f"estimates_{_today()}.json"


def _is_expo():
    """Return True when ?expo=1 is present in the query string."""
    return request.args.get("expo") == "1"


def _expo_qs():
    """Return the query-string suffix to propagate expo mode in links."""
    return "?expo=1" if _is_expo() else ""


def _random_index():
    estimates = _load_json(_estimates_path())
    keys = list(estimates.keys())
    if not keys:
        return 0
    return random.randint(0, len(keys) - 1)


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    """Landing page with navigation buttons."""
    return render_template("home.html")


@app.route("/play/")
@app.route("/play/<int:index>")
def play_combo(index=0):
    expo = _is_expo()
    estimates = _load_json(_estimates_path())
    if not estimates:
        return_url = request.path + ("?expo=1" if expo else "")
        return render_template(
            "loading.html",
            message="Waiting for today's data to be generated. Please wait...",
            return_url=return_url,
        )

    day_data = _load_json(DATA_DIR / "day_data.json")
    global_data = _load_json(DATA_DIR / "global.json")

    keys = list(estimates.keys())
    if index >= len(keys):
        index = 0
    entry = estimates.get(keys[index], {})

    avg = day_data.get(_today(), {}).get("average_liters", 0.5)

    return render_template(
        "combined.html",
        current_index=index,
        total_videos=len(keys),
        video_data=entry.get("video_data", {}),
        estimate=entry.get("estimate", {}),
        metadata=entry.get("metadata", {}),
        today_data=day_data.get(_today(), {}),
        global_data=global_data,
        average_today=avg,
        expo=expo,
        expo_qs=_expo_qs(),
    )


@app.route("/play/random")
def play_random():
    index = _random_index()
    url = url_for("play_combo", index=index)
    if _is_expo():
        url += "?expo=1"
    return redirect(url)


@app.route("/video/play/")
@app.route("/video/play/<int:index>")
def play_video(index=0):
    expo = _is_expo()
    if not expo:
        return redirect(url_for("play_combo", index=index))
    estimates = _load_json(_estimates_path())
    if not estimates:
        return_url = request.path + ("?expo=1" if expo else "")
        return render_template(
            "loading.html",
            message="Waiting for today's data to be generated. Please wait...",
            return_url=return_url,
        )

    keys = list(estimates.keys())
    if index >= len(keys):
        index = 0
    entry = estimates.get(keys[index], {})

    return render_template(
        "video.html",
        current_index=index,
        total_videos=len(keys),
        metadata=entry.get("metadata", {}),
        expo=expo,
        expo_qs=_expo_qs(),
    )


@app.route("/video/play/random")
def play_video_random():
    index = _random_index()
    url = url_for("play_video", index=index)
    if _is_expo():
        url += "?expo=1"
    return redirect(url)


@app.route("/data/play/")
@app.route("/data/play/<int:index>")
def play_data(index=0):
    expo = _is_expo()
    if not expo:
        return redirect(url_for("play_combo", index=index))
    estimates = _load_json(_estimates_path())
    if not estimates:
        return_url = request.path + ("?expo=1" if expo else "")
        return render_template(
            "loading.html",
            message="Waiting for today's data to be generated. Please wait...",
            return_url=return_url,
        )

    day_data = _load_json(DATA_DIR / "day_data.json")
    global_data = _load_json(DATA_DIR / "global.json")
    keys = list(estimates.keys())
    if index >= len(keys):
        index = 0
    entry = estimates.get(keys[index], {})

    avg = day_data.get(_today(), {}).get("average_liters", 0.5)

    return render_template(
        "data.html",
        current_index=index,
        total_videos=len(keys),
        video_data=entry.get("video_data", {}),
        estimate=entry.get("estimate", {}),
        metadata=entry.get("metadata", {}),
        today_data=day_data.get(_today(), {}),
        global_data=global_data,
        average_today=avg,
        expo=expo,
        expo_qs=_expo_qs(),
    )


@app.route("/data/play/random")
def play_data_random():
    index = _random_index()
    url = url_for("play_data", index=index)
    if _is_expo():
        url += "?expo=1"
    return redirect(url)


@app.route("/global")
def global_view():
    expo = _is_expo()
    if not expo:
        return redirect(url_for("play_combo", index=0))
    global_data = _load_json(DATA_DIR / "global.json")
    day_data = _load_json(DATA_DIR / "day_data.json")
    avg = day_data.get(_today(), {}).get("average_liters", 0.5)
    return render_template(
        "global.html",
        global_data=global_data,
        average_today=avg,
        expo=expo,
        expo_qs=_expo_qs(),
    )


@app.route("/info")
def info_view():
    """Display the info PDF (only linked from the home page)."""
    return render_template("info.html")


@app.route("/about")
def about_view():
    """About us page."""
    return render_template("about.html")


@app.route("/research")
def research_view():
    """Research page."""
    return render_template("research.html")


@app.route("/timeline")
def timeline_view():
    """Timeline page."""
    return render_template("timeline.html")


@app.route("/contact")
def contact_view():
    """Contact page."""
    return render_template("contact.html")


@app.route("/installation")
def installation_view():
    """5L installation page."""
    return render_template("installation.html")


@app.route("/data-explorer")
def data_explorer_view():
    """File explorer for the data folder."""
    day_data = _load_json(DATA_DIR / "day_data.json")

    files = []
    for p in sorted(DATA_DIR.iterdir()):
        if p.suffix == ".json" and not p.name.startswith(".") and p.name != "global.json":
            entry = {"name": p.name, "size": p.stat().st_size}
            m = __import__('re').match(r'^estimates_(\d{4}-\d{2}-\d{2})\.json$', p.name)
            if m and m.group(1) in day_data:
                dd = day_data[m.group(1)]
                total = dd.get("total_liters", 0)
                if total == 0:
                    n = dd.get("n_images_videos", dd.get("n_images", 0))
                    total = round(n * dd.get("average_liters", 0), 2)
                entry["total_liters"] = total
            files.append(entry)

    # Build chart data: per-day total liters + max-liters video URL
    chart_points = []
    for date_str in sorted(day_data.keys()):
        dd = day_data[date_str]
        total = dd.get("total_liters", 0)
        if total == 0:
            # Fallback: average * n_images
            n = dd.get("n_images_videos", dd.get("n_images", 0))
            avg = dd.get("average_liters", 0)
            total = round(n * avg, 2)

        # Find the max-liters video for the day
        est_path = DATA_DIR / f"estimates_{date_str}.json"
        max_video_url = None
        if est_path.exists():
            estimates = _load_json(est_path)
            max_liters = -1
            for entry in estimates.values():
                wl = entry.get("estimate", {}).get("w_tot_l", 0)
                if wl > max_liters:
                    max_liters = wl
                    max_video_url = entry.get("metadata", {}).get("url")

        chart_points.append({
            "date": date_str,
            "liters": round(total, 2),
            "video_url": max_video_url,
        })

    return render_template("data_explorer.html", files=files, chart_data=chart_points)


@app.route("/api/data-file/<path:filename>")
def api_data_file(filename):
    """Return contents of a JSON file from the data folder."""
    # Sanitize: only allow .json files, no path traversal
    safe_name = Path(filename).name
    if not safe_name.endswith(".json") or safe_name != filename:
        return jsonify({"error": "Invalid filename"}), 400
    file_path = DATA_DIR / safe_name
    if not file_path.exists():
        return jsonify({"error": "File not found"}), 404
    data = _load_json(file_path)
    return jsonify(data)


@app.route("/data/info.pdf")
def serve_info_pdf():
    """Serve the PDF file from the data directory."""
    return send_from_directory(DATA_DIR, "info.pdf")


# ── API ─────────────────────────────────────────────────────────────────────

@app.route("/api/reload")
def reload_data():
    """Polled by loading.html to detect when data becomes available."""
    estimates = _load_json(_estimates_path())
    return_url = request.args.get("return_url", "/")
    return jsonify({
        "success": True,
        "total_videos": len(estimates),
        "has_data": len(estimates) > 0,
        "return_url": return_url,
    })


# ── Template filters ────────────────────────────────────────────────────────

@app.template_filter("format_number")
def format_number(value):
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return "0"


# ── SocketIO events ─────────────────────────────────────────────────────────

@socketio.on("video_control")
def handle_video_control(data):
    emit("sync_video", data, broadcast=True, include_self=False)


@socketio.on("change_video")
def handle_change_video(data):
    emit("sync_index", data, broadcast=True, include_self=True)


# ── Standalone ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=8081,
                 use_reloader=True, allow_unsafe_werkzeug=True)

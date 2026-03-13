"""
5 Litros – Water‐consumption estimator for AI‐generated videos.

Architecture
────────────
* Flask + SocketIO web server runs in a **background daemon thread**.
* The main thread runs a continuous fetch→estimate loop every 15 minutes.
* Both threads share data via JSON files on disk (no in‑memory coupling).
* Every individual API / ffprobe call is wrapped in try/except so a
  single bad video never crashes the whole process.
"""

import json
import signal
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from fetch import fetch_top_civitai_images, fetch_filtered_videos
from fetch import download_media, get_file_extension
from water_consumption_estimate import (
    calculate_water_consumption_estimate,
    get_video_properties,
)

# ── Graceful shutdown ───────────────────────────────────────────────────────
_shutdown = threading.Event()


def _handle_signal(signum, frame):
    print(f"\n⏹  Received signal {signum}, shutting down…")
    _shutdown.set()


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Main application ───────────────────────────────────────────────────────
class WaterEstimatorApp:
    def __init__(self, limit=10, period="Day", sort="Most Reactions",
                 output_dir="./data", nsfw=False, type="video"):
        self.limit = limit
        self.period = period
        self.sort = sort
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.nsfw = nsfw
        self.type = type
        self.socketio_instance = None

    # ── workflow ────────────────────────────────────────────────────────
    def run_full_workflow(self):
        """Fetch → estimate → save.  Never raises."""
        print("=" * 60)
        print(f"Starting workflow at {datetime.now():%Y-%m-%d %H:%M:%S}")
        print("=" * 60)

        # 1) Fetch ---------------------------------------------------------
        images_data = fetch_top_civitai_images(
            limit=self.limit,
            period=self.period,
            sort=self.sort,
            type=self.type,
            nsfw=self.nsfw,
        )
        if not images_data or not images_data.get("items"):
            print("No data returned from API – skipping this cycle.")
            return

        today = datetime.now().strftime("%Y-%m-%d")

        # 2) Load / initialise estimates -----------------------------------
        estimates_file = self.output_dir / f"estimates_{today}.json"
        estimates = {}
        if estimates_file.exists():
            try:
                with open(estimates_file, "r") as f:
                    estimates = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"  ⚠ Could not read {estimates_file}: {e}")
                estimates = {}

        n = len(estimates)

        # 3) Estimate new videos -------------------------------------------
        self._update_estimates(images_data, estimates, n)

        # 4) Persist estimates ---------------------------------------------
        try:
            with open(estimates_file, "w") as f:
                json.dump(estimates, f, indent=2)
            print(f"Estimates saved → {estimates_file}")
        except IOError as e:
            print(f"  ✗ Failed to write estimates: {e}")

        # 5) Aggregate day‑level stats ------------------------------------
        self._update_day_data(today, estimates)

        # 6) Notify connected browsers ------------------------------------
        if self.socketio_instance:
            try:
                self.socketio_instance.emit(
                    "data_updated",
                    {"date": today, "total_videos": len(estimates)},
                )
            except Exception:
                pass  # non-critical

    def _update_estimates(self, images_data, estimates, n):
        known_ids = set()
        for key in estimates:
            entry = estimates[key]
            if isinstance(entry, dict) and "metadata" in entry:
                known_ids.add(entry["metadata"].get("id"))

        for item in images_data["items"]:
            item_id = item.get("id")
            if item_id in known_ids:
                continue

            try:
                result = self._estimate_single(item)
                if result is None:
                    continue
                estimates[str(n)] = result
                n += 1
            except Exception as e:
                print(f"  ✗ Error estimating {item_id}: {e}")
                traceback.print_exc()

    def _estimate_single(self, item):
        """Return an estimate dict for one API item, or None to skip."""
        item_id = item.get("id", "?")
        print(f"  Estimating {item_id}…")

        # Prompt / steps
        meta = item.get("meta") or {}
        prompt = meta.get("prompt") or "No prompt provided."
        n_words = len(prompt.split()) if prompt else 70
        n_steps = meta.get("steps", 25) or 25

        # Video properties via ffprobe (URL)
        url = item.get("url", "")
        video_data = get_video_properties(url) if url else None

        if not video_data:
            video_data = {
                "duration": 5,
                "width": item.get("width", 768),
                "height": item.get("height", 768),
                "fps": 30,
            }

        if video_data["fps"] == 0:
            video_data["fps"] = 30

        if video_data["duration"] >= 60:
            print(f"  ⚠ Skipping {item_id}: duration {video_data['duration']:.1f}s > 60s")
            return None

        width = video_data.get("width", 768)
        height = video_data.get("height", 768)
        resolution_factor = (width * height) / (768 * 768) / 3

        estimate = calculate_water_consumption_estimate(
            Video=True,
            video_duration=video_data["duration"],
            frames_per_second=max(1.0, min(video_data["fps"], 90.0)),
            n_palabras_por_prompt=n_words,
            n_steps=n_steps,
            T_step=resolution_factor,
        )

        return {
            "video_data": video_data,
            "estimate": estimate,
            "metadata": {
                "id": item.get("id", ""),
                "url": url,
                "created_at": item.get("createdAt", ""),
                "created_by": item.get("username", ""),
                "prompt": prompt,
                "steps": n_steps,
            },
        }

    def _update_day_data(self, today, estimates):
        day_file = self.output_dir / "day_data.json"
        all_data = {}
        if day_file.exists():
            try:
                with open(day_file, "r") as f:
                    all_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                all_data = {}

        total_liters = 0.0
        total_duration = 0.0
        count = 0
        for entry in estimates.values():
            if not isinstance(entry, dict):
                continue
            est = entry.get("estimate", {})
            vd = entry.get("video_data", {})
            total_liters += est.get("w_tot_l", 0)
            total_duration += vd.get("duration", 0)
            count += 1

        all_data[today] = {
            "n_images_videos": count,
            "total_duration_seconds": total_duration,
            "total_liters": total_liters,
            "average_liters": total_liters / count if count > 0 else 0.0,
        }

        try:
            with open(day_file, "w") as f:
                json.dump(all_data, f, indent=2)
            print(f"Day data saved → {day_file}")
        except IOError as e:
            print(f"  ✗ Failed to write day data: {e}")

    # ── continuous loop ─────────────────────────────────────────────────
    def run_continuous(self, interval=900):
        """Run fetch→estimate in a loop.  Catches all exceptions."""
        while not _shutdown.is_set():
            try:
                self.run_full_workflow()
            except Exception:
                print("═" * 60)
                print("UNHANDLED ERROR IN WORKFLOW – will retry next cycle")
                traceback.print_exc()
                print("═" * 60)

            print(f"\nSleeping {interval}s until next cycle…\n")
            if _shutdown.wait(timeout=interval):
                break  # woke up early because of shutdown signal

        print("Worker loop exited.")

    # ── Flask server ────────────────────────────────────────────────────
    def start_flask_server(self):
        from web_app import app, socketio
        self.socketio_instance = socketio
        socketio.run(
            app,
            debug=False,
            host="0.0.0.0",
            port=8081,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )


# ── XXX-mode application ───────────────────────────────────────────────────
class WaterEstimatorXXX:
    """
    Alternative workflow (mode=xxx):
    - Once per day, fetch up to *target_videos* videos whose prompt has
      at least *min_prompt_words* words.
    - Download each video file locally so the web app works offline.
    - Estimate water consumption for every qualifying video.
    - Sleep until the next calendar day.
    """

    def __init__(self, config):
        self.target = config.get("target_videos", 400)
        self.min_words = config.get("min_prompt_words", 20)
        self.sort = config.get("sort", "Most Reactions")
        self.period = config.get("period", "Day")
        self.nsfw = config.get("nsfw", True)
        self.output_dir = Path(config.get("output_dir", "./data"))
        self.downloads_dir = Path(config.get("downloads_dir", "../downloads"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.socketio_instance = None

    # ── single-day workflow ─────────────────────────────────────────
    def run_daily_workflow(self):
        """Fetch → filter → estimate → download.  Never raises."""
        today = datetime.now().strftime("%Y-%m-%d")
        print("=" * 60)
        print(f"[xxx] Starting daily workflow for {today}")
        print("=" * 60)

        # 1) Load existing estimates (resume support) ─────────────────
        estimates_file = self.output_dir / f"estimates_{today}.json"
        estimates = {}
        if estimates_file.exists():
            try:
                with open(estimates_file, "r") as f:
                    estimates = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"  ⚠ Could not read {estimates_file}: {e}")
                estimates = {}

        known_ids = set()
        for entry in estimates.values():
            if isinstance(entry, dict) and "metadata" in entry:
                known_ids.add(entry["metadata"].get("id"))

        remaining = self.target - len(estimates)
        if remaining <= 0:
            print(f"[xxx] Already have {len(estimates)} videos for today – nothing to do.")
            return

        print(f"[xxx] Need {remaining} more videos (have {len(estimates)}/{self.target})")

        # 2) Fetch filtered videos from API ──────────────────────────
        result = fetch_filtered_videos(
            target=remaining,
            min_prompt_words=self.min_words,
            period=self.period,
            sort=self.sort,
            nsfw=self.nsfw,
            known_ids=known_ids,
        )

        if not result or not result.get("items"):
            print("[xxx] No qualifying videos returned from API.")
            self._update_day_data(today, estimates)
            return

        # 3) Estimate + download each qualifying video ───────────────
        day_dl_dir = self.downloads_dir / today / "videos"
        day_dl_dir.mkdir(parents=True, exist_ok=True)

        n = len(estimates)
        for item in result["items"]:
            if _shutdown.is_set():
                break
            try:
                entry = self._estimate_single(item)
                if entry is None:
                    continue

                # Download the video file locally
                url = item.get("url", "")
                if url:
                    ext = get_file_extension(url, default_ext=".mp4")
                    local_filename = f"{n}{ext}"
                    local_path = day_dl_dir / local_filename
                    if not local_path.exists():
                        ok = download_media(url, local_path, item.get("id"), "video")
                        if not ok:
                            print(f"  ⚠ Download failed for {item.get('id')} – keeping estimate anyway")
                    entry["local_video"] = f"{today}/videos/{local_filename}"

                    # Also save metadata json alongside video
                    meta_path = day_dl_dir / f"{n}_metadata.json"
                    try:
                        with open(meta_path, "w", encoding="utf-8") as mf:
                            json.dump(item, mf, indent=2, ensure_ascii=False)
                    except IOError:
                        pass

                estimates[str(n)] = entry
                n += 1

                # Persist after every video (crash-safe)
                if n % 10 == 0:
                    self._save_estimates(estimates_file, estimates)

            except Exception as e:
                print(f"  ✗ Error processing {item.get('id')}: {e}")
                traceback.print_exc()

        # 4) Final persist ────────────────────────────────────────────
        self._save_estimates(estimates_file, estimates)
        self._update_day_data(today, estimates)

        # 5) Notify connected browsers ───────────────────────────────
        if self.socketio_instance:
            try:
                self.socketio_instance.emit(
                    "data_updated",
                    {"date": today, "total_videos": len(estimates)},
                )
            except Exception:
                pass

        print(f"[xxx] ✓ Day complete: {len(estimates)} videos estimated & downloaded.")

    def _estimate_single(self, item):
        """Return an estimate dict for one API item, or None to skip."""
        item_id = item.get("id", "?")
        print(f"  [xxx] Estimating {item_id}…")

        meta = item.get("meta") or {}
        prompt = meta.get("prompt") or "No prompt provided."
        n_words = len(prompt.split()) if prompt else 70
        n_steps = meta.get("steps", 25) or 25

        url = item.get("url", "")
        video_data = get_video_properties(url) if url else None

        if not video_data:
            video_data = {
                "duration": 5,
                "width": item.get("width", 768),
                "height": item.get("height", 768),
                "fps": 30,
            }

        if video_data["fps"] == 0:
            video_data["fps"] = 30

        if video_data["duration"] >= 60:
            print(f"  ⚠ Skipping {item_id}: duration {video_data['duration']:.1f}s > 60s")
            return None

        width = video_data.get("width", 768)
        height = video_data.get("height", 768)
        resolution_factor = (width * height) / (768 * 768) / 3

        estimate = calculate_water_consumption_estimate(
            Video=True,
            video_duration=video_data["duration"],
            frames_per_second=max(1.0, min(video_data["fps"], 90.0)),
            n_palabras_por_prompt=n_words,
            n_steps=n_steps,
            T_step=resolution_factor,
        )

        return {
            "video_data": video_data,
            "estimate": estimate,
            "metadata": {
                "id": item.get("id", ""),
                "url": url,
                "created_at": item.get("createdAt", ""),
                "created_by": item.get("username", ""),
                "prompt": prompt,
                "steps": n_steps,
            },
        }

    def _save_estimates(self, path, estimates):
        try:
            with open(path, "w") as f:
                json.dump(estimates, f, indent=2)
            print(f"  Estimates saved → {path} ({len(estimates)} entries)")
        except IOError as e:
            print(f"  ✗ Failed to write estimates: {e}")

    def _update_day_data(self, today, estimates):
        day_file = self.output_dir / "day_data.json"
        all_data = {}
        if day_file.exists():
            try:
                with open(day_file, "r") as f:
                    all_data = json.load(f)
            except (json.JSONDecodeError, IOError):
                all_data = {}

        total_liters = 0.0
        total_duration = 0.0
        count = 0
        for entry in estimates.values():
            if not isinstance(entry, dict):
                continue
            est = entry.get("estimate", {})
            vd = entry.get("video_data", {})
            total_liters += est.get("w_tot_l", 0)
            total_duration += vd.get("duration", 0)
            count += 1

        all_data[today] = {
            "n_images_videos": count,
            "total_duration_seconds": total_duration,
            "total_liters": total_liters,
            "average_liters": total_liters / count if count > 0 else 0.0,
        }

        try:
            with open(day_file, "w") as f:
                json.dump(all_data, f, indent=2)
            print(f"  Day data saved → {day_file}")
        except IOError as e:
            print(f"  ✗ Failed to write day data: {e}")

    # ── continuous loop (once per day) ──────────────────────────────
    def run_continuous(self):
        """Run once-a-day workflow.  Sleep until next midnight + 5 min."""
        while not _shutdown.is_set():
            try:
                self.run_daily_workflow()
            except Exception:
                print("═" * 60)
                print("[xxx] UNHANDLED ERROR IN WORKFLOW – will retry next cycle")
                traceback.print_exc()
                print("═" * 60)

            # Calculate seconds until next day 00:05
            now = datetime.now()
            import datetime as _dt
            tomorrow = (now + _dt.timedelta(days=1)).replace(
                hour=0, minute=5, second=0, microsecond=0
            )
            sleep_secs = (tomorrow - now).total_seconds()
            print(f"\n[xxx] Sleeping {sleep_secs:.0f}s until {tomorrow:%Y-%m-%d %H:%M}…\n")
            if _shutdown.wait(timeout=sleep_secs):
                break

        print("[xxx] Worker loop exited.")

    # ── Flask server ────────────────────────────────────────────────
    def start_flask_server(self):
        from web_app import app, socketio
        self.socketio_instance = socketio
        socketio.run(
            app,
            debug=False,
            host="0.0.0.0",
            port=8081,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )


# ── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Accept optional config path as CLI argument:
    #   python main.py                      → uses config/config.json  (default mode)
    #   python main.py config/config_xxx.json → uses xxx mode
    config_path = sys.argv[1] if len(sys.argv) > 1 else "./config/config.json"
    with open(config_path, "r") as f:
        config = json.load(f)

    mode = config.get("mode", "default")
    print(f"Starting Water Estimator App  [mode={mode}]")
    print(f"  Config ({config_path}): {json.dumps(config, indent=2)}")

    # Write mode marker so web_app can detect which mode is active
    mode_marker = Path("./data/.mode")
    mode_marker.parent.mkdir(parents=True, exist_ok=True)
    mode_marker.write_text(mode)

    if mode == "xxx":
        # ── XXX mode: once-a-day, 400 filtered videos, local downloads ──
        app = WaterEstimatorXXX(config)

        flask_thread = threading.Thread(target=app.start_flask_server, daemon=True)
        flask_thread.start()
        print("Flask server started on :8081  [xxx mode]")

        app.run_continuous()
    else:
        # ── Default mode: fetch every 15 minutes ────────────────────────
        app = WaterEstimatorApp(
            limit=config.get("limit", 200),
            type=config.get("type", "video"),
            nsfw=config.get("nsfw", False),
            sort=config.get("sort", "Newest"),
            period=config.get("period", "Day"),
        )

        flask_thread = threading.Thread(target=app.start_flask_server, daemon=True)
        flask_thread.start()
        print("Flask server started on :8081")

        app.run_continuous()

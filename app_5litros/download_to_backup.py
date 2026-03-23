"""
Download videos from an estimates JSON file into the backup folder,
creating one metadata JSON per video. Numbering continues from the
highest existing file in the backup directory.
"""

import json
import os
import sys
import requests
from pathlib import Path

ESTIMATES_FILE = "data/estimates_2026-02-21.json"
BACKUP_DIR = Path("../downloads/backup")


def get_next_index(backup_dir):
    """Return the next available numeric index based on existing *_metadata.json files."""
    max_idx = 0
    for f in backup_dir.glob("*_metadata.json"):
        try:
            idx = int(f.stem.replace("_metadata", ""))
            if idx > max_idx:
                max_idx = idx
        except ValueError:
            continue
    return max_idx + 1


def main():
    with open(ESTIMATES_FILE, "r", encoding="utf-8") as f:
        estimates = json.load(f)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    next_idx = get_next_index(BACKUP_DIR)
    total = len(estimates)
    downloaded = 0
    failed = 0

    print(f"Estimates entries: {total}")
    print(f"Backup dir: {BACKUP_DIR.resolve()}")
    print(f"Starting at index: {next_idx}\n")

    for key in sorted(estimates.keys(), key=int):
        entry = estimates[key]
        meta = entry.get("metadata", {})
        video_data = entry.get("video_data", {})
        url = meta.get("url", "")

        if not url:
            print(f"  [{key}] No URL, skipping")
            failed += 1
            continue

        # Build backup-style metadata JSON
        backup_meta = {
            "id": meta.get("id"),
            "url": url,
            "width": video_data.get("width"),
            "height": video_data.get("height"),
            "type": "video",
            "createdAt": meta.get("created_at"),
            "meta": {
                "prompt": meta.get("prompt", ""),
                "steps": meta.get("steps"),
            },
            "username": meta.get("created_by", ""),
        }

        video_path = BACKUP_DIR / f"{next_idx}.mp4"
        meta_path = BACKUP_DIR / f"{next_idx}_metadata.json"

        try:
            print(f"  [{key}/{total}] Downloading id {meta.get('id')} -> {next_idx}.mp4 ...", end=" ", flush=True)
            resp = requests.get(url, stream=True, timeout=60)
            resp.raise_for_status()
            with open(video_path, "wb") as vf:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        vf.write(chunk)
            size_mb = os.path.getsize(video_path) / (1024 * 1024)
            print(f"{size_mb:.2f} MB")
        except Exception as e:
            print(f"FAILED: {e}")
            if video_path.exists():
                video_path.unlink()
            failed += 1
            continue

        with open(meta_path, "w", encoding="utf-8") as mf:
            json.dump(backup_meta, mf, indent=2, ensure_ascii=False)

        downloaded += 1
        next_idx += 1

    print(f"\nDone. Downloaded: {downloaded}, Failed: {failed}, Total: {total}")


if __name__ == "__main__":
    main()

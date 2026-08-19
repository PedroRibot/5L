import requests
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse


def fetch_top_civitai_images(limit=10, period="Day", sort="Most Reactions",
                             type="video", nsfw=False):
    """
    Fetch top images/videos from Civitai API with pagination support.

    The Civitai API returns a max of 200 items per request.  If *limit* > 200
    this function paginates automatically using the cursor the API provides.
    Includes retry logic with exponential back-off.
    """
    base_url = "https://civitai.com/api/v1/images"
    all_items = []
    page_size = min(limit, 200)
    cursor = None
    max_retries = 3

    while len(all_items) < limit:
        remaining = limit - len(all_items)
        params = {
            "limit": min(page_size, remaining),
            "sort": sort,
            "period": period,
            "nsfw": nsfw,
            "type": type,
            "withMeta": True,  # required for Civitai to include the generation "meta" (prompt, steps...)
        }
        if cursor:
            params["cursor"] = cursor

        data = None
        for attempt in range(1, max_retries + 1):
            try:
                print(f"  Fetching batch ({len(all_items)}/{limit}) "
                      f"from Civitai (attempt {attempt})...")
                response = requests.get(base_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                break
            except requests.exceptions.RequestException as e:
                print(f"  ✗ Request failed (attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    print("  ✗ All retries exhausted.")
                    if all_items:
                        print(f"  Returning {len(all_items)} items collected so far.")
                        return {"items": all_items}
                    return None
                wait = 2 ** attempt
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)

        if data is None:
            break

        items = data.get("items", [])
        if not items:
            print("  No more items returned by API.")
            break

        all_items.extend(items)
        print(f"  ✓ Got {len(items)} items (total: {len(all_items)}/{limit})")

        metadata = data.get("metadata", {})
        cursor = metadata.get("nextCursor")
        if not cursor:
            print("  No more pages available.")
            break

        # Be polite to the API between pages
        time.sleep(1.0)

    print(f"✓ Successfully retrieved {len(all_items)} items total\n")
    return {"items": all_items[:limit]}


def _load_filler_cursor(state_path):
    try:
        with open(state_path, "r") as f:
            return json.load(f).get("cursor")
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return None


def _save_filler_cursor(state_path, cursor):
    try:
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        with open(state_path, "w") as f:
            json.dump({"cursor": cursor}, f)
    except IOError as e:
        print(f"  ⚠ Could not persist filler cursor: {e}")


def fetch_filler_videos(needed, exclude_ids, min_age_days=15, nsfw=False,
                        type="video", state_path="data/filler_state.json",
                        max_pages=40):
    """
    Top up a day's videos with older, random Civitai items that satisfy:
      1) createdAt is more than *min_age_days* days in the past.
      2) item has non-empty meta.prompt.

    Civitai's API has no date-filter param, so this walks `sort=Random`
    pages via cursor (persisted on disk) until enough qualifying items are
    found. The cursor position naturally drifts further into the past as
    it advances, so each call continues where the last one left off
    instead of re-scanning the same recent pages.
    """
    if needed <= 0:
        return []

    base_url = "https://civitai.com/api/v1/images"
    cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)
    exclude_ids = set(exclude_ids)
    collected = []
    cursor = _load_filler_cursor(state_path)

    for page in range(max_pages):
        if len(collected) >= needed:
            break

        params = {
            "limit": 200,
            "sort": "Random",
            "period": "AllTime",
            "nsfw": nsfw,
            "type": type,
            "withMeta": True,
        }
        if cursor:
            params["cursor"] = cursor

        try:
            print(f"  Fetching filler page {page + 1}/{max_pages} "
                  f"({len(collected)}/{needed} found)...")
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Filler request failed: {e}")
            break

        items = data.get("items", [])
        if not items:
            cursor = None  # exhausted history, wrap around next time
            break

        for item in items:
            item_id = item.get("id")
            if item_id in exclude_ids:
                continue

            meta = item.get("meta") or {}
            if not meta.get("prompt"):
                continue

            created_at = item.get("createdAt", "")
            try:
                created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                continue
            if created_dt > cutoff:
                continue

            exclude_ids.add(item_id)
            collected.append(item)
            if len(collected) >= needed:
                break

        cursor = data.get("metadata", {}).get("nextCursor")
        if not cursor:
            break  # reached the end of Civitai's history, wrap around next time

        time.sleep(1.0)  # be polite to the API between pages

    _save_filler_cursor(state_path, cursor)
    print(f"✓ Filler fetch collected {len(collected)}/{needed} videos\n")
    return collected[:needed]


def load_backup_data(backup_dir="../downloads/backup"):
    """
    Read local metadata JSON files from the backup directory and return them
    in the same {"items": [...]} format as the Civitai API.
    """
    backup_path = Path(backup_dir)
    if not backup_path.is_dir():
        print(f"  ✗ Backup directory not found: {backup_path.resolve()}")
        return None

    items = []
    for meta_file in sorted(backup_path.glob("*_metadata.json")):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                item = json.load(f)
            items.append(item)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  ⚠ Skipping {meta_file.name}: {e}")

    if not items:
        print("  ✗ No valid metadata files found in backup.")
        return None

    print(f"✓ Loaded {len(items)} items from backup\n")
    return {"items": items}


def download_media(url, save_path, item_id, media_type="image"):
    """Download an image or video from URL with progress tracking."""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        total_size = int(response.headers.get("content-length", 0))
        with open(save_path, "wb") as f:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
        if total_size > 0:
            print(f"  ✓ Downloaded {media_type} {item_id}: "
                  f"{total_size / 1024 / 1024:.2f} MB")
        else:
            file_size = os.path.getsize(save_path)
            print(f"  ✓ Downloaded {media_type} {item_id}: "
                  f"{file_size / 1024 / 1024:.2f} MB")
        return True
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Error downloading {media_type} {item_id}: {e}")
        return False
    except Exception as e:
        print(f"  ✗ Unexpected error downloading {media_type} {item_id}: {e}")
        return False


def get_file_extension(url, default_ext=".jpg"):
    """Extract file extension from URL."""
    parsed_url = urlparse(url)
    path = parsed_url.path
    _, ext = os.path.splitext(path)
    valid_extensions = [
        ".jpg", ".jpeg", ".png", ".gif", ".webp",
        ".mp4", ".webm", ".mov",
    ]
    if ext.lower() in valid_extensions:
        return ext.lower()
    return default_ext


def download_all_media(images_data, output_dir="civitai_downloads"):
    """Download all images/videos from the fetched data."""
    if not images_data or "items" not in images_data:
        print("No image data to download")
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path(output_dir) / today
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    videos_dir = output_dir / "videos"
    images_dir.mkdir(exist_ok=True)
    videos_dir.mkdir(exist_ok=True)

    items = images_data["items"]
    stats = {
        "total": len(items),
        "images_downloaded": 0,
        "videos_downloaded": 0,
        "failed": 0,
    }

    for idx, item in enumerate(items, 1):
        item_id = item.get("id", f"unknown_{idx}")
        url = item.get("url", "")
        if not url:
            stats["failed"] += 1
            continue

        file_ext = get_file_extension(url)
        is_video = file_ext in [".mp4", ".webm", ".mov"]
        save_dir = videos_dir if is_video else images_dir
        media_type = "video" if is_video else "image"
        save_path = save_dir / f"{idx}{file_ext}"

        success = download_media(url, save_path, item_id, media_type)
        if success:
            if is_video:
                stats["videos_downloaded"] += 1
            else:
                stats["images_downloaded"] += 1
            meta_file = save_dir / f"{idx}_metadata.json"
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(item, f, indent=2, ensure_ascii=False)
        else:
            stats["failed"] += 1

    return stats

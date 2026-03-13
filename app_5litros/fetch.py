import requests
import json
import os
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def _nsfw_param(nsfw):
    """Convert a Python bool / string nsfw config value to the Civitai
    API's NsfwLevel enum string.  The API accepts: None, Soft, Mature, X.
    Python's requests serialises False → "False" (capital F) which the
    API rejects, so we do the conversion explicitly."""
    if isinstance(nsfw, bool):
        return "X" if nsfw else "None"
    return str(nsfw)  # pass-through for string enum values


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
            "nsfw": _nsfw_param(nsfw),
            "type": type,
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


def fetch_filtered_videos(target=400, min_prompt_words=20, period="Day",
                          sort="Most Reactions", nsfw=True, known_ids=None):
    """
    Fetch videos from Civitai API, filtering for prompts with at least
    *min_prompt_words* words.  Paginates until *target* qualifying,
    deduplicated videos are collected (or the API runs out of pages).

    Parameters
    ----------
    target : int
        Number of qualifying videos to collect.
    min_prompt_words : int
        Minimum word count in the prompt metadata.
    known_ids : set | None
        IDs already processed – these are skipped to avoid duplicates.

    Returns
    -------
    dict   {"items": [list of qualifying API items]}
    """
    base_url = "https://civitai.com/api/v1/images"
    accepted = []
    seen_ids = set(known_ids or [])
    cursor = None
    max_retries = 3
    page_size = 200  # max allowed by Civitai API
    total_fetched = 0
    total_rejected = 0

    print(f"[xxx] Fetching filtered videos: target={target}, "
          f"min_prompt_words={min_prompt_words}")

    while len(accepted) < target:
        params = {
            "limit": page_size,
            "sort": sort,
            "period": period,
            "nsfw": _nsfw_param(nsfw),
            "type": "video",
        }
        if cursor:
            params["cursor"] = cursor

        data = None
        for attempt in range(1, max_retries + 1):
            try:
                print(f"  [xxx] Fetching page (accepted {len(accepted)}/{target}, "
                      f"fetched {total_fetched}) attempt {attempt}…")
                response = requests.get(base_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                break
            except requests.exceptions.RequestException as e:
                print(f"  ✗ Request failed (attempt {attempt}/{max_retries}): {e}")
                if attempt == max_retries:
                    print("  ✗ All retries exhausted for this page.")
                    if accepted:
                        print(f"  Returning {len(accepted)} accepted items so far.")
                        return {"items": accepted}
                    return None
                wait = 2 ** attempt
                print(f"  Retrying in {wait}s…")
                time.sleep(wait)

        if data is None:
            break

        items = data.get("items", [])
        if not items:
            print("  [xxx] No more items returned by API.")
            break

        total_fetched += len(items)

        for item in items:
            if len(accepted) >= target:
                break

            item_id = item.get("id")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            # Filter: prompt must have >= min_prompt_words words
            meta = item.get("meta") or {}
            prompt = meta.get("prompt", "") or ""
            word_count = len(prompt.split())
            if word_count < min_prompt_words:
                total_rejected += 1
                continue

            accepted.append(item)

        print(f"  [xxx] Page done — accepted {len(accepted)}/{target} "
              f"(rejected {total_rejected} for short prompt)")

        metadata = data.get("metadata", {})
        cursor = metadata.get("nextCursor")
        if not cursor:
            print("  [xxx] No more pages available from API.")
            break

        # Be polite to the API between pages
        time.sleep(1.0)

    print(f"[xxx] ✓ Finished: {len(accepted)} qualifying videos "
          f"from {total_fetched} total fetched "
          f"({total_rejected} rejected for short prompt)\n")
    return {"items": accepted}


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

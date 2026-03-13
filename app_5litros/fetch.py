import requests
import json
import os
import time
from datetime import datetime
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
        # requests serialises Python bools as "True"/"False" (capital)
        # but the Civitai API expects lowercase "true"/"false" or a
        # string level like "Mature".
        nsfw_param = str(nsfw).lower() if isinstance(nsfw, bool) else nsfw
        params = {
            "limit": min(page_size, remaining),
            "sort": sort,
            "period": period,
            "nsfw": nsfw_param,
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


def _interleave_evenly(primary, secondary):
    """Insert *secondary* items evenly throughout *primary*.

    For example, 100 primary + 10 secondary → one secondary item inserted
    roughly every 10 primary items so they never appear in a block.
    """
    if not secondary:
        return list(primary)
    if not primary:
        return list(secondary)

    result = []
    # Divide primary into (M+1) equal chunks, inserting one secondary
    # item after each of the first M chunks.
    gap = len(primary) / (len(secondary) + 1)
    sec_idx = 0
    next_insert = gap

    for i, item in enumerate(primary):
        result.append(item)
        if sec_idx < len(secondary) and (i + 1) >= next_insert:
            result.append(secondary[sec_idx])
            sec_idx += 1
            next_insert += gap

    # Safety: append any remaining secondary items
    result.extend(secondary[sec_idx:])
    return result


def fetch_mixed_sfw_mature(limit=200, period="Day", sort="Newest",
                           type="video", mature_ratio=1 / 3):
    """Fetch SFW *and* Mature content and merge them.

    * Two separate API calls (SFW with ``nsfw=False``, Mature with
      ``nsfw="Mature"``).
    * Mature items are capped so they never exceed *mature_ratio* of the
      combined result.
    * Mature items are spread evenly among the SFW items (no blocks).
    """
    # ── 1. Fetch SFW items ───────────────────────────────────────────
    print("── Fetching SFW content ──")
    sfw_data = fetch_top_civitai_images(
        limit=limit, period=period, sort=sort, type=type, nsfw=False,
    )
    sfw_items = sfw_data.get("items", []) if sfw_data else []

    if not sfw_items:
        return {"items": []}

    sfw_ids = {item.get("id") for item in sfw_items}

    # Max mature items: mature_ratio = M / (S + M) → M = S·r/(1−r)
    max_mature = int(len(sfw_items) * mature_ratio / (1 - mature_ratio))
    if max_mature < 1:
        return {"items": sfw_items}

    # ── 2. Fetch Mature-level content ────────────────────────────────
    # nsfw="Mature" tells the API to include items up to Mature level,
    # so the response will contain SFW + Soft + Mature items.
    print("── Fetching Mature content ──")
    mature_data = fetch_top_civitai_images(
        limit=limit, period=period, sort=sort, type=type, nsfw="Mature",
    )
    mature_raw = mature_data.get("items", []) if mature_data else []

    # ── 3. Keep only truly non-SFW items, remove duplicates ──────────
    mature_items = [
        item for item in mature_raw
        if item.get("id") not in sfw_ids
    ]

    # ── 4. Cap to maintain the ratio ─────────────────────────────────
    mature_items = mature_items[:max_mature]

    if not mature_items:
        print("  No mature items found after filtering.")
        return {"items": sfw_items}

    # ── 5. Interleave evenly ─────────────────────────────────────────
    merged = _interleave_evenly(sfw_items, mature_items)

    print(f"✓ Mixed result: {len(sfw_items)} SFW + {len(mature_items)} Mature "
          f"= {len(merged)} total")
    return {"items": merged}


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

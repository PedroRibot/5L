import requests
import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

def fetch_top_civitai_images(limit=10, period="Day", sort="Most Reactions", type="video", nsfw=False):
    """Fetch top images from Civitai API based on reactions."""
    
    base_url = "https://civitai.com/api/v1/images"
    
    params = {
        "limit": limit,
        "sort": sort,
        "period": period,
        "nsfw": nsfw,
        "type": type
        
    }
    
    try:
        print(f"Fetching top {limit} images from Civitai...")
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        
        data = response.json()
        print(f"✓ Successfully retrieved {len(data.get('items', []))} images\n")
        
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from Civitai API: {e}")
        return None

def download_media(url, save_path, item_id, media_type="image"):
    """Download an image or video from URL with progress tracking."""
    
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        
        with open(save_path, 'wb') as f:
            downloaded = 0
            chunk_size = 8192
            
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"  Downloading {media_type} {item_id}: {percent:.1f}%", end='\r')
        
        if total_size > 0:
            print(f"  ✓ Downloaded {media_type} {item_id}: {total_size / 1024 / 1024:.2f} MB")
        else:
            file_size = os.path.getsize(save_path)
            print(f"  ✓ Downloaded {media_type} {item_id}: {file_size / 1024 / 1024:.2f} MB")
        
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
    
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp4', '.webm', '.mov']
    
    if ext.lower() in valid_extensions:
        return ext.lower()
    
    return default_ext

def download_all_media(images_data, output_dir="downloads"):
    """Download all images/videos from the fetched data."""
    
    if not images_data or 'items' not in images_data:
        print("No image data to download")
        return None
    
    # Create output directory structure
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    images_dir = Path(output_dir) / "images"
    videos_dir = Path(output_dir) / "videos"
    metadata_dir = Path(output_dir) / "metadata"
    
    images_dir.mkdir(exist_ok=True)
    videos_dir.mkdir(exist_ok=True)
    metadata_dir.mkdir(exist_ok=True)
    
    items = images_data['items']
    
    stats = {
        'total': len(items),
        'images_downloaded': 0,
        'videos_downloaded': 0,
        'failed': 0
    }
    
    print("=" * 80)
    print(f"DOWNLOADING {len(items)} MEDIA FILES")
    print("=" * 80)
    
    for idx, item in enumerate(items, 1):
        item_id = item.get('id', f'unknown_{idx}')
        url = item.get('url', '')
        
        if not url:
            print(f"[{idx}/{len(items)}] ✗ No URL for item {item_id}")
            stats['failed'] += 1
            continue
        
        file_ext = get_file_extension(url)
        is_video = file_ext in ['.mp4', '.webm', '.mov']
        
        if is_video:
            save_dir = videos_dir
            media_type = "video"
        else:
            save_dir = images_dir
            media_type = "image"
        
        filename = f"{item_id}_{idx}{file_ext}"
        save_path = save_dir / filename
        
        print(f"\n[{idx}/{len(items)}] Item ID: {item_id}")
        
        success = download_media(url, save_path, item_id, media_type)
        
        if success:
            if is_video:
                stats['videos_downloaded'] += 1
            else:
                stats['images_downloaded'] += 1
            
            # Save metadata
            metadata_file = metadata_dir / f"{item_id}_metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(item, f, indent=2, ensure_ascii=False)
        else:
            stats['failed'] += 1
    
    return stats

def display_download_summary(stats):
    """Display summary of download operations."""
    
    if not stats:
        return
    
    print("\n" + "=" * 80)
    print("DOWNLOAD SUMMARY")
    print("=" * 80)
    print(f"Total items: {stats['total']}")
    print(f"Images downloaded: {stats['images_downloaded']}")
    print(f"Videos downloaded: {stats['videos_downloaded']}")
    print(f"Failed downloads: {stats['failed']}")
    
    total_success = stats['images_downloaded'] + stats['videos_downloaded']
    if stats['total'] > 0:
        success_rate = (total_success / stats['total']) * 100
        print(f"Success rate: {success_rate:.1f}%")
    
    print("=" * 80)

def save_full_metadata(images_data, output_dir="downloads"):
    """Save complete API response to JSON file."""
    
    metadata_path = Path(output_dir) / "full_response.json"
    
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(images_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ Full metadata saved to {metadata_path}")

def main():
    """Main function to run the Civitai downloader."""
    
    print("=" * 80)
    print("CIVITAI TOP IMAGES DOWNLOADER")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Configuration
    LIMIT = 100
    PERIOD = "Day"
    SORT = "Most Reactions"
    OUTPUT_DIR = "civitai_downloads"
    NSFW = True
    IMGTYPE = "video"
    
    print(f"Configuration:")
    print(f"  - Limit: {LIMIT} items")
    print(f"  - Period: {PERIOD}")
    print(f"  - Sort: {SORT}")
    print(f"  - Output: {OUTPUT_DIR}/\n")
    print(f"  - Output: {OUTPUT_DIR}/\n")
    
    # Fetch and download
    images_data = fetch_top_civitai_images(limit=LIMIT, period=PERIOD, sort=SORT, type=IMGTYPE, nsfw=NSFW)
    
    if not images_data:
        print("Failed to retrieve images from Civitai API")
        return
    
    save_full_metadata(images_data, OUTPUT_DIR)
    stats = download_all_media(images_data, OUTPUT_DIR)
    display_download_summary(stats)
    
    print(f"\nFiles saved to: {OUTPUT_DIR}/")
    print(f"  - images/     : Downloaded image files")
    print(f"  - videos/     : Downloaded video files")
    print(f"  - metadata/   : Individual item metadata (JSON)")
    print(f"  - full_response.json : Complete API response")

if __name__ == "__main__":
    main()

# app_5litros/main.py
from datetime import datetime
from pathlib import Path
from fetch import fetch_top_civitai_images, download_all_media  # Import from your modules
from water_consumption_estimate import get_video_properties, calculate_water_consumption_estimate
import json

class WaterEstimatorApp:

    def __init__(self, limit=10, period="Day", sort="Most Reactions", output_dir="../downloads", nsfw=False):
        self.limit = limit
        self.period = period
        self.sort = sort
        self.output_dir = Path(output_dir)
        self.nsfw = nsfw
    
    def run_full_workflow(self):
        """Run the complete workflow: fetch, download, and estimate."""
        print("Starting full workflow...")
        
        # Step 1: Fetch data
        images_data = fetch_top_civitai_images(
            limit=self.limit, period=self.period, sort=self.sort, type="video"
        )
        if not images_data:
            print("Failed to fetch data.")
            return
        
        # Step 2: Download media
        stats = download_all_media(images_data, self.output_dir)
        if not stats:
            print("Download failed.")
            return
        
        # Step 3: Run estimation on downloaded videos
        today = datetime.now().strftime('%Y-%m-%d')
        video_dir = self.output_dir / today / "videos"
        estimates = {}
        if video_dir.exists():
            for video_file in sorted(video_dir.glob("*.mp4")):
                print(f"Estimating for {video_file.name}...")
                try:
                    video_data = get_video_properties(str(video_file))
                    estimate = calculate_water_consumption_estimate(
                        Video=True,
                        video_duration=video_data["duration"],
                        frames_per_second=video_data["fps"],
                        n_palabras_por_prompt=70.0,
                        n_steps=25.0
                    )
                    estimates[video_file.name] = {
                        "video_data": video_data,
                        "estimate": estimate
                    }
                except Exception as e:
                    print(f"Error estimating {video_file.name}: {e}")
        
        # Save estimates to JSON
        estimates_file = self.output_dir / today / "estimates.json"
        with open(estimates_file, 'w') as f:
            json.dump(estimates, f, indent=2)
        
        print(f"Estimates saved to {estimates_file}")
        
    def run_continuous(self):
        """Run continuously, downloading new videos at the start of each day."""
        import time
        last_date = None
        while True:
            current_date = datetime.now().strftime('%Y-%m-%d')
            if current_date != last_date:
                print(f"New day detected: {current_date}")
                self.run_full_workflow()
                last_date = current_date
            time.sleep(3600)  # Check every hour

if __name__ == "__main__":
    app = WaterEstimatorApp(limit=100)  # Download 100 videos
    app.run_continuous()  # Run continuously, downloading daily
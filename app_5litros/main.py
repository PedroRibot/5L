# app_5litros/main.py
from datetime import datetime
from pathlib import Path
from fetch import fetch_top_civitai_images, download_all_media  # Import from your modules
from water_consumption_estimate import get_video_properties, calculate_water_consumption_estimate
import json

class WaterEstimatorApp:

    def __init__(self, limit=10, period="Day", sort="Most Reactions", output_dir="../downloads", nsfw=False, type="video"):
        self.limit = limit
        self.period = period
        self.sort = sort
        self.output_dir = Path(output_dir)
        self.nsfw = nsfw
        self.type = type
    
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
        
        today = datetime.now().strftime('%Y-%m-%d')

        # all_data = self.output_dir / today / f"all_fetched_data_{today}.json"
        # with open(all_data, 'w') as f:
        #     json.dump(images_data, f, indent=2)

        # Step 2: Run estimation on downloaded videos
        estimates = {}
        n= 0
        for item in images_data['items']: 
            print(f"Estimating for {item['id']}...")

            prompt = ""
            n_palabras_por_prompt = 70
            n_steps = 25
            video_data = None

            if item.get("meta"):
                prompt = item.get("meta", {}).get("prompt")
                n_palabras_por_prompt = len(prompt.split()) if prompt else 70
                n_steps = item.get("meta", {}).get("steps", 25)
            else:
                prompt = "There was no prompt found"
                n_palabras_por_prompt = 70
                n_steps = 25

            video_data = get_video_properties(str(item['url']))
            if not video_data:
                print(f"Error estimating {item['id']}: Could not retrieve video properties")
                video_data = {"duration": 5, "width": item.get("width", 768), "height": item.get("height", 768), "fps": 30}
                
            # Calculate resolution factor based on dimensions
            width = video_data.get("width", 768)
            height = video_data.get("height", 768)
            resolution = width * height 

            new_metadata = {
                "id": item.get("id", ""),
                "url" : item.get("url", ""),
                "created_at": item.get("createdAt", ""),
                "prompt": prompt,
                "steps": n_steps
            }
            
            resolution_factor = resolution / (768 * 768) / 3 

            estimate = calculate_water_consumption_estimate(
                Video=True,
                video_duration=video_data["duration"] if video_data else 5.0,
                frames_per_second=video_data["fps"] if video_data else 30.0,
                n_palabras_por_prompt=n_palabras_por_prompt,
                n_steps=n_steps,
                T_step=resolution_factor
            )

            estimates[n] = {
                "video_data": video_data,
                "estimate": estimate,
                "metadata": new_metadata,
            }
            n += 1
        
        # Save estimates to JSON
        estimates_file = self.output_dir / f"estimates_{today}.json"
        with open(estimates_file, 'w') as f:
            json.dump(estimates, f, indent=2)
        

        print(f"Estimates saved to {estimates_file}")

    def run_continuous(self):
        """Run continuously, downloading new videos at the start of each day."""
        import time
        last_date = None
        while True:
            current_date = datetime.now().strftime('%Y-%m-%d')
            print(f"CHECKING DATE: {current_date}, LAST DATE: {last_date}")
            if current_date != last_date:
                print(f"New day detected: {current_date}")
                self.run_full_workflow()
                last_date = current_date
            time.sleep(3600)  # Check every hour

if __name__ == "__main__":
    app = WaterEstimatorApp(limit=200, type="video", nsfw=False)  
    app.run_continuous()  
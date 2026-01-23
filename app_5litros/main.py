# app_5litros/main.py
from datetime import datetime
from pathlib import Path
from fetch import fetch_top_civitai_images, download_all_media
from water_consumption_estimate import get_video_properties, calculate_water_consumption_estimate, calculate_water_average
import json
import threading

class WaterEstimatorApp:

    def __init__(self, limit=10, period="Day", sort="Most Reactions", output_dir="./data", nsfw=False, type="video"):
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
                
            if video_data["fps"] == 0:
                video_data["fps"] = 30
            
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
            fps = video_data["fps"] if video_data else 30.0

            estimate = calculate_water_consumption_estimate(
                Video=True,
                video_duration=video_data["duration"] if video_data else 5.0,
                frames_per_second=max(1.0, min(fps, 90.0)),
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
        

        average = calculate_water_average(estimates)
        average_file = self.output_dir / "day_data.json"

        # Load existing data or create empty dict
        if average_file.exists():
            with open(average_file, 'r') as f:
                all_data = json.load(f)
        else:
            all_data = {}

        # Add or update today's data
        all_data[today] = {
            "n_images_videos": self.limit,
            "average_liters": average
        }

        # Save back to file
        with open(average_file, 'w') as f:
            json.dump(all_data, f, indent=2)

        print(f"Day data saved to {average_file}")


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

    def start_flask_server(self):
        """Start Flask server in a separate thread"""
        from web_app import socketio, app
        socketio.run(app, debug=False, host='0.0.0.0', port=8081, 
                     use_reloader=False, allow_unsafe_werkzeug=True)

if __name__ == "__main__":
    app = WaterEstimatorApp(limit=200, type="video", nsfw=False, sort="Most Reactions", period="Day")  

    # Start Flask server in background thread
    flask_thread = threading.Thread(target=app.start_flask_server, daemon=True)
    flask_thread.start()
    print("Flask server started in background")

    app.run_continuous()  
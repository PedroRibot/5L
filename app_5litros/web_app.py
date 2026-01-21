from flask import Flask, render_template, send_from_directory
from pathlib import Path
import json
from datetime import datetime

app = Flask(__name__)

# Path to downloads
DOWNLOADS_DIR = Path("../downloads")
TODAY = datetime.now().strftime('%Y-%m-%d')
ESTIMATES_FILE = DOWNLOADS_DIR / f"estimates_{TODAY}.json"

# Load estimates
def load_estimates():
    if ESTIMATES_FILE.exists():
        with open(ESTIMATES_FILE, 'r') as f:
            return json.load(f)
    return {}

estimates = load_estimates()

@app.route('/')
@app.route('/play/<int:index>')
def play_video(index=0):
    if not estimates:
        return "No videos found. Please run the download workflow first."
    
    if index >= len(estimates):
        index = 0

    video_name = list(estimates.keys())[index]
    video_data = estimates.get(video_name, {}).get('video_data', {})
    estimate = estimates.get(video_name, {}).get('estimate', {})
    metadata = estimates.get(video_name, {}).get('metadata', {})
    
    return render_template('index.html',
                          current_index=index,
                          total_videos=len(estimates),
                          video_data=video_data,
                          estimate=estimate,
                          metadata=metadata
                          )


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8081)
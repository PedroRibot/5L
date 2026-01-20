from flask import Flask, render_template, send_from_directory
from pathlib import Path
import json
from datetime import datetime

app = Flask(__name__)

# Path to downloads
DOWNLOADS_DIR = Path("../downloads")
TODAY = datetime.now().strftime('%Y-%m-%d')
VIDEO_DIR = DOWNLOADS_DIR / TODAY / "videos"
IMAGE_DIR = DOWNLOADS_DIR / TODAY / "images"
ESTIMATES_FILE = DOWNLOADS_DIR / TODAY / "estimates.json"

# Load estimates
def load_estimates():
    if ESTIMATES_FILE.exists():
        with open(ESTIMATES_FILE, 'r') as f:
            return json.load(f)
    return {}

estimates = load_estimates()
video_files = sorted([f for f in VIDEO_DIR.glob("*.mp4") if f.name in estimates]) if VIDEO_DIR.exists() else []

@app.route('/')
@app.route('/play/<int:index>')
def play_video(index=0):
    if not video_files:
        return "No videos found. Please run the download workflow first."
    
    if index >= len(video_files):
        index = 0
    
    video_name = video_files[index].name
    video_data = estimates.get(video_name, {}).get('video_data', {})
    estimate = estimates.get(video_name, {}).get('estimate', {})
    metadata = estimates.get(video_name, {}).get('metadata', {})
    n_palabras_por_prompt = estimates.get(video_name, {}).get('n_palabras_por_prompt', 70)
    n_steps = estimates.get(video_name, {}).get('n_steps', 25)
    T_step = estimates.get(video_name, {}).get('T_step', 0.4)
    
    return render_template('index.html',
                          current_index=index,
                          total_videos=len(video_files),
                          video_files=[f.name for f in video_files],
                          video_data=video_data,
                          estimate=estimate,
                          metadata=metadata,
                          n_palabras_por_prompt=n_palabras_por_prompt,
                          n_steps=n_steps,
                          T_step=T_step)

@app.route('/video/<filename>')
def serve_video(filename):
    return send_from_directory(VIDEO_DIR, filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8081)
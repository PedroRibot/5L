from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from pathlib import Path
import json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

DOWNLOADS_DIR = Path("../downloads")
TODAY = datetime.now().strftime('%Y-%m-%d')
ESTIMATES_FILE = DOWNLOADS_DIR / f"estimates_{TODAY}.json"

def load_estimates():
    if ESTIMATES_FILE.exists():
        with open(ESTIMATES_FILE, 'r') as f:
            return json.load(f)
    return {}

estimates = load_estimates()

@app.route('/')
@app.route('/video/play/<int:index>')
@app.route('/data/play/<int:index>')
@app.route('/play/<int:index>')
def play_video(index=0):
    if not estimates:
        return "No videos found."
    
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
                          metadata=metadata)

# Socket event handlers
@socketio.on('video_control')
def handle_video_control(data):
    """Broadcast video control events to all clients"""
    emit('sync_video', data, broadcast=True, include_self=False)

@socketio.on('change_video')
def handle_change_video(data):
    """Broadcast video index changes to all clients"""
    emit('sync_index', data, broadcast=True, include_self=True)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8081, 
                 use_reloader=True, allow_unsafe_werkzeug=True)

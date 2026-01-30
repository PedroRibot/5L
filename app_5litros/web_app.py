from flask import Flask, render_template, jsonify, session
from flask_socketio import SocketIO, emit
from pathlib import Path
from flask import request
import json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

DOWNLOADS_DIR = Path("./data")
TODAY = datetime.now().strftime('%Y-%m-%d')
ESTIMATES_FILE = DOWNLOADS_DIR / f"estimates_{TODAY}.json"
DAY_DATA_FILE = DOWNLOADS_DIR / "day_data.json"
GLOBAL_DATA_FILE = DOWNLOADS_DIR / "global.json"

def load_data(file_path):
    if file_path.exists():
        with open(file_path, 'r') as f:
            return json.load(f)
    return {}

# Initial load
estimates = load_data(ESTIMATES_FILE)
day_data = load_data(DAY_DATA_FILE)
global_data = load_data(GLOBAL_DATA_FILE)

@app.route('/')
@app.route('/video/play/')
@app.route('/video/play/<int:index>')
@app.route('/data/play/')
@app.route('/data/play/<int:index>')
@app.route('/data/video/play/')
@app.route('/data/video/play/<int:index>')
def play_video(index=0):
    # Reload estimates to get latest data
    current_estimates = load_data(ESTIMATES_FILE)
    
    if not current_estimates:
        session['return_url'] = request.path
        return render_template('loading.html', message="Waiting for today's data to be generated. Please wait...")
    
    session.pop('return_url', None)
    
    if index >= len(current_estimates):
        index = 0
    
    video_name = list(current_estimates.keys())[index]
    video_data = current_estimates.get(video_name, {}).get('video_data', {})
    estimate = current_estimates.get(video_name, {}).get('estimate', {})
    metadata = current_estimates.get(video_name, {}).get('metadata', {})
    
    return render_template('index.html',
                         current_index=index,
                         total_videos=len(current_estimates),
                         video_data=video_data,
                         estimate=estimate,
                         metadata=metadata,
                         today_data=day_data.get(TODAY, {}))

@app.route('/api/reload')
def reload_data():
    """API endpoint to reload data"""
    global estimates, day_data, global_data
    estimates = load_data(ESTIMATES_FILE)
    day_data = load_data(DAY_DATA_FILE)
    global_data = load_data(GLOBAL_DATA_FILE)
    
    # Get the return URL from session, default to '/'
    return_url = session.get('return_url', '/')
    
    return jsonify({
        'success': True,
        'total_videos': len(estimates),
        'has_data': len(estimates) > 0,
        'return_url': return_url
    })


@app.route('/global')
def global_view():
    return render_template('global.html',
                         global_data=global_data,
                         average_today=day_data.get(TODAY, {}).get('average_liters', 0.5))

@app.template_filter('format_number')
def format_number(value):
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return "0"

# Socket event handlers
@socketio.on('video_control')
def handle_video_control(data):
    """Broadcast video control events to all clients"""
    emit('sync_video', data, broadcast=True, include_self=False)

@socketio.on('change_video')
def handle_change_video(data):
    """Broadcast video index changes to all clients"""
    print("New video coming: ", data)
    emit('sync_index', data, broadcast=True, include_self=True)

@socketio.on('check_more_videos')
def handle_more_videos_request():
    """Handle request for more videos when current list is exhausted"""
    print("Client requested more videos - list exhausted")
    emit('more_videos_response', {'message': 'Feature coming soon', 'action': 'reload'}, broadcast=False, include_self=False)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=8081,
                use_reloader=True, allow_unsafe_werkzeug=True)

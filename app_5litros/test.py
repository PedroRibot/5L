from datetime import datetime
import json
from pathlib import Path
import water_consumption_estimate

# Your actual data structure

DOWNLOADS_DIR = Path("./data")
TODAY = datetime.now().strftime('%Y-%m-%d')
ESTIMATES_FILE = DOWNLOADS_DIR / f"estimates_{TODAY}.json"

def load_estimates():
    if ESTIMATES_FILE.exists():
        with open(ESTIMATES_FILE, 'r') as f:
            return json.load(f)
    return {}

estimates = load_estimates()

result = water_consumption_estimate.calculate_water_average(estimates)
print(f"Result: {result}")  # Should print ~0.162289
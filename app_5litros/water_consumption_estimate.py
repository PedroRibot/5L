import requests
import json
import os
import subprocess
import re
from datetime import datetime
from pathlib import Path

## Water Consumption Estimate for AI Model Inference
## Estimates using as if they were using SDXL 1.0 model parameters
Potencia_Efectiva = 0.41
I_grid = 2.5
WUE = 1.0
PUE = 1.65
Token_Latency = 0.01 

def get_video_properties(video_path):
    """Extract duration, resolution, and fps from mp4 file."""
    video_path = Path(video_path)
    
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", 
         "format=duration:stream=width,height,r_frame_rate",
         "-of", "default=noprint_wrappers=1", str(video_path)],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        return None
    
    data = result.stdout
    duration_match = re.search(r'duration=([\d.]+)', data)
    width_match = re.search(r'width=(\d+)', data)
    height_match = re.search(r'height=(\d+)', data)
    fps_match = re.search(r'r_frame_rate=(\d+)/(\d+)', data)
    
    if not all([duration_match, width_match, height_match, fps_match]):
        return None
    
    duration = float(duration_match.group(1))
    width = int(width_match.group(1))
    height = int(height_match.group(1))
    fps = int(fps_match.group(1)) / int(fps_match.group(2)) if int(fps_match.group(2)) != 0 else 0
    
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps
    }


def calculate_water_consumption_estimate(Video = True, video_duration=5.0, frames_per_second=30.0, n_palabras_por_prompt=70.0, n_steps=25.0, T_step = 0.4):

    N_tokens = n_palabras_por_prompt / 4 
    Latencia = (Token_Latency * N_tokens) + (n_steps * T_step)  
    Keyframes_generados = video_duration * frames_per_second * 0.15 if Video else 4.0

    Factor_de_entrenamiento = 1.2

    energia_imagen = (Latencia * Potencia_Efectiva / 3600) * Keyframes_generados * Factor_de_entrenamiento 
    energia_data_center = energia_imagen * PUE
    water_for_energy_l = energia_imagen * I_grid
    water_for_data_center_l = energia_data_center * WUE
    w_tot_l = water_for_energy_l + water_for_data_center_l
    
    return {
        "energia_imagen": energia_imagen,
        "energia_data_center": energia_data_center,
        "water_for_energy_l": water_for_energy_l,
        "water_for_data_center_l": water_for_data_center_l,
        "w_tot_l": w_tot_l,
    }

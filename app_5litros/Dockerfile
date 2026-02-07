FROM python:3.11-slim

WORKDIR /app

# ffmpeg / ffprobe for video metadata extraction
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data /app/config

EXPOSE 8081

CMD ["python", "-u", "main.py"]

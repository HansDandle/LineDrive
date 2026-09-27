FROM python:3.12-slim

LABEL org.opencontainers.image.title="LineDrive" \
      org.opencontainers.image.description="DVR, program guide and recording assistant for HDHomeRun tuners" \
      org.opencontainers.image.source="https://github.com/HansDandle/LineDrive" \
      org.opencontainers.image.licenses="MIT"

# ffmpeg records and encodes the tuner streams; tzdata makes TZ work
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# config.json lives in /config (LineDrive creates it on first run; the schedule and guide cache go
# in /config/data). Recordings go to /recordings. Set TZ to your time zone, e.g. America/Chicago.
ENV PYTHONUNBUFFERED=1 \
    LINEDRIVE_DOCKER=1 \
    LINEDRIVE_RECORDINGS=/recordings \
    TZ=UTC
VOLUME ["/config", "/recordings"]
WORKDIR /config
EXPOSE 5050
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5050/api/status', timeout=4)" || exit 1
CMD ["python", "/app/dvr_web.py"]

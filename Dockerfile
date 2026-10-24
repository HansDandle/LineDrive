# Comskip (marks commercial breaks; off unless turned on in Settings) isn't packaged for Debian,
# so build it against the same ffmpeg libraries the final image installs
FROM python:3.12-slim AS comskip
ARG COMSKIP_COMMIT=a140b6ac8bc8f596729e9052819affc779c3b377
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential autoconf automake libtool pkg-config \
       git ca-certificates libargtable2-dev libavformat-dev libavcodec-dev libavutil-dev libswscale-dev \
    && git clone https://github.com/erikkaashoek/Comskip /src \
    && cd /src && git checkout "$COMSKIP_COMMIT" \
    && ./autogen.sh && ./configure && make -j"$(nproc)" \
    && install -m 755 comskip /usr/local/bin/comskip

FROM python:3.12-slim

LABEL org.opencontainers.image.title="LineDrive" \
      org.opencontainers.image.description="DVR, program guide and recording assistant for HDHomeRun tuners" \
      org.opencontainers.image.source="https://github.com/HansDandle/LineDrive" \
      org.opencontainers.image.licenses="MIT"

# ffmpeg records and encodes the tuner streams; tzdata makes TZ work
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tzdata libargtable2-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=comskip /usr/local/bin/comskip /usr/local/bin/comskip

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

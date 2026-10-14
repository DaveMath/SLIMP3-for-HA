FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH
LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache python3 py3-aiohttp py3-numpy ffmpeg

# Informational only: record what this ffmpeg offers. The app re-checks at startup and logs clearly.
RUN (ffmpeg -hide_banner -version; ffmpeg -hide_banner -encoders) > /tmp/ffmpeg-info.txt 2>&1 || true; \
    head -1 /tmp/ffmpeg-info.txt; \
    grep -i mp3 /tmp/ffmpeg-info.txt || echo "note: no MP3 encoder listed by this ffmpeg"; \
    rm -f /tmp/ffmpeg-info.txt

COPY app /app
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]

FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH
LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache python3 py3-aiohttp py3-numpy ffmpeg

# Fail the build early if ffmpeg cannot encode MP3 (the SLIMP3 decodes MP3 only).
RUN ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libmp3lame \
 || { echo "ERROR: this ffmpeg build lacks the libmp3lame encoder" >&2; exit 1; }

COPY app /app
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]

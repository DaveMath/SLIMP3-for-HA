FROM ghcr.io/home-assistant/base:latest

ARG BUILD_VERSION
ARG BUILD_ARCH
ENV SLIMP3_VERSION=${BUILD_VERSION}
LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}"

RUN apk add --no-cache python3 py3-aiohttp py3-numpy py3-pip ffmpeg

# Optional HomePod support (reads what a HomePod is playing). Prebuilt packages only, so no compiler is needed. The
# compiled 'miniaudio' package (pyatv uses it only to stream audio TO speakers) has no prebuilt package for this
# platform, so it is left out and the app supplies a stand-in. If anything here fails, the app still builds and runs
# without HomePod support.
RUN pip install --no-cache-dir --break-system-packages --only-binary=:all: --no-deps "pyatv==0.18.0" \
 && pip install --no-cache-dir --break-system-packages --only-binary=:all: \
      chacha20poly1305-reuseable cryptography ifaddr protobuf pydantic requests srptools tabulate tinytag zeroconf \
 || echo "note: HomePod support was not installed (the app will run without it)"

# Google Cast discovery needs the same zeroconf package, kept in its own step so Cast still finds devices if HomePod
# support could not be installed. Without it, addresses listed under cast_ips still work.
RUN pip install --no-cache-dir --break-system-packages --only-binary=:all: zeroconf \
 || echo "note: zeroconf was not installed (Cast devices must be listed under cast_ips)"

# Informational only: record what this ffmpeg offers. The app re-checks at startup and logs clearly.
RUN (ffmpeg -hide_banner -version; ffmpeg -hide_banner -encoders) > /tmp/ffmpeg-info.txt 2>&1 || true; \
    head -1 /tmp/ffmpeg-info.txt; \
    grep -i mp3 /tmp/ffmpeg-info.txt || echo "note: no MP3 encoder listed by this ffmpeg"; \
    rm -f /tmp/ffmpeg-info.txt

COPY app /app
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]

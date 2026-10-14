#!/usr/bin/with-contenv bashio

bashio::log.info "Starting SLIMP3 Player"
cd /app
exec python3 -u main.py

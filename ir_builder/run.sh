#!/usr/bin/with-contenv bashio
set -e
bashio::log.info "Starting the IR Builder add-on..."
bashio::log.info "Using python from: $(which python3)"
if [ -z "$SUPERVISOR_TOKEN" ]; then
    bashio::log.fatal "SUPERVISOR_TOKEN is not set. Add-on cannot connect to the Supervisor API."
    exit 1
else
    bashio::log.info "SUPERVISOR_TOKEN is successfully set. Add-on has access to the Supervisor API."
fi
#exec python3 /app/app.py
exec /opt/venv/bin/python3 /app/app/app.py
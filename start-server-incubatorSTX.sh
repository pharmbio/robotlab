#!/usr/bin/env bash

#
# Startup script for webserver
#
echo "Activate venv"
source "/pharmbio/labrobots-restserver/venv/bin/activate"

echo "Start webserver"
python /pharmbio/labrobots-restserver/server-incubatorSTX.py
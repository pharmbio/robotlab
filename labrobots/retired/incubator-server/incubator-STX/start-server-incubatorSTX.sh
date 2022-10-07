#!/usr/bin/env bash

#
# Startup script for webserver
#
echo "Activate venv"
source "/pharmbio/labrobots-restserver/incubator-STX/venv/bin/activate"

echo "Start webserver"
python /pharmbio/labrobots-restserver/incubator-STX/server-incubatorSTX.py
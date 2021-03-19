#!/bin/sh
set -xeuo pipefail

trap 'kill $(jobs -p)' EXIT

ssh -N -L   "30001:$ROBOT_IP:30001" -l "$JUMPHOST_USER" "$JUMPHOST" -p "$JUMPHOST_PORT"

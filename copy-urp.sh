#!/bin/sh
set -xeuo pipefail
mkdir -p programs
scp -p -o "ProxyJump=$JUMPHOST_USER@$JUMPHOST:$JUMPHOST_PORT" "root@$ROBOT_IP:/data/programs/dan_*" programs/

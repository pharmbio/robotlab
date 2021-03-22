#!/bin/sh
set -xeuo pipefail
mkdir -p scripts
scp -p -o "ProxyJump=$JUMPHOST_USER@$JUMPHOST:$JUMPHOST_PORT" "root@$ROBOT_IP:/data/scripts/dan_*" scripts/

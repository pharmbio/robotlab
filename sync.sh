#!/bin/sh
rsync -rtuv ./* robotlab:robot-remote-control
rsync -rtuv robotlab:robot-remote-control/ .

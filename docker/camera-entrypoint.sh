#!/usr/bin/env bash
set -eo pipefail
umask 0002
mkdir -p "$HOME" "$ROS_LOG_DIR"
source /opt/ros/jazzy/setup.bash
source /opt/orbbec_ws/install/setup.bash
exec "$@"

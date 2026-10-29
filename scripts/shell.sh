#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="gemini-isaac-ros:4.6-jazzy"
exec docker run --rm -it --gpus all --shm-size=2g \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp/isaac-home -e ROS_DOMAIN_ID=112 \
  -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
  --mount "type=bind,src=$ROOT,dst=/workspaces/isaac_ros-dev" \
  --workdir /workspaces/isaac_ros-dev "$IMAGE" -lc \
  'mkdir -p "$HOME"; source /opt/ros/jazzy/setup.bash; exec bash'

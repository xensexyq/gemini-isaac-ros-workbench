#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "$(docker version --format '{{.Server.Platform.Name}}')" == 'Docker Engine - Community' ]] || { echo '需要 Docker Engine - Community。' >&2; exit 1; }
BASE="$(docker image inspect gemini-isaac-ros:4.6-jazzy --format '{{index .Config.Labels "io.gemini-workbench.base"}}')"
[[ "$BASE" == isaac-ros-4.6-jazzy ]] || { echo '请先运行 scripts/build_image.sh 构建本项目基础镜像。' >&2; exit 1; }
python3 "$ROOT/scripts/prepare.py" driver
docker build --network host --progress plain \
  --output type=image,compression=uncompressed,push=false \
  -t gemini-isaac-ros:4.6-jazzy-camera-v2.10.6 \
  -f "$ROOT/docker/Dockerfile.camera" "$ROOT/docker"

# Legacy Gemini 330 firmware compatibility stays inside a derived image.
docker build --network none --progress plain \
  -t gemini-isaac-ros:4.6-jazzy-camera-parity \
  -f "$ROOT/docker/Dockerfile.parity" "$ROOT/docker"

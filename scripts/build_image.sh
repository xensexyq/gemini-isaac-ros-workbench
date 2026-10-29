#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "$(docker version --format '{{.Server.Platform.Name}}')" == 'Docker Engine - Community' ]] || { echo '需要 Docker Engine - Community。' >&2; exit 1; }
python3 "$ROOT/scripts/prepare.py" examples
docker build --network host --progress plain \
  --output type=image,compression=uncompressed,push=false \
  -t gemini-isaac-ros:4.6-jazzy -f "$ROOT/docker/Dockerfile" "$ROOT/docker"

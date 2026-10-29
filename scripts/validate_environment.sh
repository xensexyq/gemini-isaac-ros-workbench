#!/usr/bin/env bash
# 官方数据集回放检查；不映射 USB，不启动相机。
set -euo pipefail
umask 0002
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-all}"
case "$MODE" in all|vslam|nvblox|gpu) ;; *) echo '用法：validate_environment.sh [all|vslam|nvblox|gpu]' >&2; exit 2;; esac
[[ "$(docker version --format '{{.Server.Platform.Name}}')" == 'Docker Engine - Community' ]] || { echo '需要 Docker Engine - Community。' >&2; exit 1; }
RUN="$ROOT/runs/$(date +%Y%m%d-%H%M%S)-dataset-validation"
ASSETS="${ISAAC_ASSETS_DIR:-$ROOT/assets}"
mkdir -p "$RUN/logs" "$RUN/reports"
NAME="gemini-isaac-replay-$$"
CREATED=0
finish() {
  CODE=$?
  if [[ "$CREATED" == 1 ]]; then docker stop --time 15 "$NAME" > "$RUN/logs/stop.log" 2>&1 || true; fi
  printf '%s\n' "$CODE" > "$RUN/reports/exit-code.txt"
  echo "检查退出码：$CODE；报告：$RUN"
}
trap finish EXIT
C_RUN="/workspaces/isaac_ros-dev/${RUN#"$ROOT/"}"
docker run --rm -d --init --name "$NAME" --network none --gpus all --shm-size=2g \
  --user "$(id -u):$(id -g)" -e HOME=/tmp/isaac-home \
  -e ROS_DOMAIN_ID=112 -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST \
  -e "ISAAC_RUN_DIR=$C_RUN" -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
  --mount "type=bind,src=$ROOT,dst=/workspaces/isaac_ros-dev" \
  --mount "type=bind,src=$ASSETS,dst=/workspaces/isaac_ros-dev/assets,readonly" \
  gemini-isaac-ros:4.6-jazzy -lc 'mkdir -p "$HOME"; exec sleep infinity'
CREATED=1
docker exec "$NAME" python3 /workspaces/isaac_ros-dev/scripts/gpu_smoke.py > "$RUN/reports/gpu.json"
if [[ "$MODE" == all || "$MODE" == vslam ]]; then
  docker exec "$NAME" bash /workspaces/isaac_ros-dev/scripts/run_vslam.sh > "$RUN/logs/vslam.log" 2>&1
fi
if [[ "$MODE" == all || "$MODE" == nvblox ]]; then
  docker exec "$NAME" bash /workspaces/isaac_ros-dev/scripts/run_nvblox.sh > "$RUN/logs/nvblox.log" 2>&1
fi

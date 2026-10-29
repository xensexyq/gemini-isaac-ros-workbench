#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME=gemini-isaac-ros-live
IMAGE=${GEMINI_CAMERA_IMAGE:-gemini-isaac-ros:4.6-jazzy-camera-parity}
LABEL=gemini-isaac-ros-workbench-v1
usage() {
  cat <<'EOF'
用法：live.sh start|stop|status|shell|doctor|visualize-stop
      live.sh camera|vslam|vio|mapping|visualize [相机序列号]
      GEMINI_PROFILE=original|persistent live.sh visualize [相机序列号]
      live.sh exec <容器内命令及参数...>
start 仅创建待命容器，不启动相机。camera/vslam/mapping 在前台运行，Ctrl+C 停止。
首次先运行 camera 检查流。visualize 自动运行 mapping，并在 http://127.0.0.1:8770/ 实时显示。
多台相机必须指定序列号。
EOF
}
owned() {
  [[ "$(docker inspect --format '{{index .Config.Labels "io.isaac-orbbec.task"}}' "$NAME" 2>/dev/null || true)" == "$LABEL" ]]
}
running() {
  owned && [[ "$(docker inspect --format '{{.State.Running}}' "$NAME")" == true ]]
}
require_running() {
  running || { echo '实机容器未运行，请先执行 live.sh start。' >&2; exit 1; }
}
action="${1:-help}"
[[ $# == 0 ]] || shift
case "$action" in
  start)
    platform="$(docker version --format '{{.Server.Platform.Name}}')"
    [[ "$platform" == 'Docker Engine - Community' ]] || { echo "需要 Docker 社区版，当前为：$platform" >&2; exit 1; }
    if docker inspect "$NAME" >/dev/null 2>&1; then
      owned || { echo '容器名称已被其他任务占用。' >&2; exit 1; }
      running || { echo '已有停止的同任务容器，请先执行 live.sh stop。' >&2; exit 1; }
      echo "容器已待命：$NAME"; exit 0
    fi
    [[ -r "$ROOT/config/fastdds.xml" ]] || { echo '缺少容器 Fast DDS 配置。' >&2; exit 1; }
    [[ -d /dev/bus/usb ]] || { echo '/dev/bus/usb 不存在，未创建容器。' >&2; exit 1; }
    docker run --rm -d --init --name "$NAME" --label "io.isaac-orbbec.task=$LABEL" \
      --gpus all --network none --shm-size=2g --memory=20g --cpus=12 \
      --user "0:$(id -g)" --cap-drop ALL --security-opt no-new-privileges:true \
      --read-only --tmpfs /tmp:rw,nosuid,size=2g \
      --device-cgroup-rule='c 189:* rw' \
      --mount type=bind,src=/dev/bus/usb,dst=/dev/bus/usb \
      --mount "type=bind,src=$ROOT,dst=/workspaces/isaac_ros-dev" \
      -e NVIDIA_DRIVER_CAPABILITIES=compute,utility \
      -e FASTRTPS_DEFAULT_PROFILES_FILE=/workspaces/isaac_ros-dev/config/fastdds.xml \
      "$IMAGE" sleep infinity
    echo "容器已待命：$NAME；尚未启动相机。"
    ;;
  stop)
    if docker inspect "$NAME" >/dev/null 2>&1; then
      owned || { echo '拒绝停止其他任务容器。' >&2; exit 1; }
      auto_remove="$(docker inspect --format '{{.HostConfig.AutoRemove}}' "$NAME")"
      docker stop --timeout 15 "$NAME"
      # --rm 容器由 Docker 自动删除；再次 inspect/rm 会与自动删除发生竞态。
      if [[ "$auto_remove" != true ]]; then docker rm "$NAME"; fi
    else
      echo '实机容器未运行。'
    fi
    ;;
  status)
    if owned; then
      docker inspect --format '状态={{.State.Status}} 镜像={{.Config.Image}} USB={{json .HostConfig.DeviceCgroupRules}}' "$NAME"
    else echo '实机容器未运行。'; fi
    ;;
  doctor)
    docker version --format '{{.Server.Platform.Name}} {{.Server.Version}}'
    docker image inspect "$IMAGE" --format '相机镜像={{.Id}}'
    df -h "$ROOT"
    if command -v lsusb >/dev/null; then lsusb; lsusb -t; fi
    echo '以上仅枚举 USB，不启动相机。连接后确认相机运行于 USB 3（5000M 或更高）。'
    ;;
  shell)
    require_running
    exec docker exec -it "$NAME" /opt/orbbec-entrypoint.sh bash
    ;;
  exec)
    require_running
    [[ $# -gt 0 ]] || { usage; exit 2; }
    exec docker exec "$NAME" /opt/orbbec-entrypoint.sh "$@"
    ;;
  visualize-stop)
    exec python3 "$ROOT/scripts/live_view.py" --stop
    ;;
  visualize)
    require_running
    [[ $# -le 1 ]] || { usage; exit 2; }
    exec python3 "$ROOT/scripts/live_view.py" --serial "${1:-}" --profile "${GEMINI_PROFILE:-baseline}"
    ;;
  camera|vslam|vio|mapping)
    require_running
    [[ $# -le 1 ]] || { usage; exit 2; }
    launch_args=("mode:=$action" "profile:=${GEMINI_PROFILE:-baseline}")
    [[ -z "${1:-}" ]] || launch_args+=("serial_number:=$1")
    # exec 的 ros2 进程保持前台；flock 防止多终端重复占用同一相机。
    exec docker exec -it "$NAME" /opt/orbbec-entrypoint.sh \
      flock --nonblock /tmp/isaac-live-pipeline.lock \
      ros2 launch /workspaces/isaac_ros-dev/scripts/orbbec_live.launch.py \
      "${launch_args[@]}"
    ;;
  help|-h|--help) usage ;;
  *) usage >&2; exit 2 ;;
esac

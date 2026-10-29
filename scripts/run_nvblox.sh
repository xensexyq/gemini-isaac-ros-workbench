#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
ROOT=/workspaces/isaac_ros-dev
RUN="${ISAAC_RUN_DIR:-$ROOT/runs/$(date +%Y%m%d-%H%M%S)-nvblox}"
mkdir -p "$RUN/logs" "$RUN/reports"
LAUNCH_PID=""
OBSERVER_PID=""
cleanup() {
  if [[ -n "$LAUNCH_PID" ]]; then
    kill -INT -- "-$LAUNCH_PID" 2>/dev/null || true
    for attempt in $(seq 1 20); do kill -0 "$LAUNCH_PID" 2>/dev/null || break; sleep 0.25; done
    if kill -0 "$LAUNCH_PID" 2>/dev/null; then kill -KILL -- "-$LAUNCH_PID" 2>/dev/null || true; fi
    wait "$LAUNCH_PID" 2>/dev/null || true
  fi
  if [[ -n "$OBSERVER_PID" ]]; then kill "$OBSERVER_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT
setsid ros2 launch "$ROOT/scripts/nvblox_static_validation.launch.py" \
  rosbag:=None num_cameras:=1 navigation:=False \
  run_rviz:=False run_foxglove:=False > "$RUN/logs/nvblox-launch.log" 2>&1 &
LAUNCH_PID=$!
python3 "$ROOT/scripts/wait_for_topic.py" /front_stereo_camera/depth/ground_truth --subscribers --timeout 90
python3 "$ROOT/scripts/observe_outputs.py" nvblox "$RUN/reports/nvblox-output.json" --seconds 55 > "$RUN/logs/nvblox-observer.log" 2>&1 &
OBSERVER_PID=$!
sleep 3
ros2 bag play "$ROOT/assets/isaac_ros_nvblox/quickstart" --clock --rate 0.25 > "$RUN/logs/nvblox-bag.log" 2>&1
wait "$OBSERVER_PID"
OBSERVER_PID=""
ros2 service list -t > "$RUN/reports/nvblox-services.txt"
timeout --kill-after=5 30 ros2 service call /nvblox_node/save_ply nvblox_msgs/srv/FilePath "{file_path: '$RUN/reports/nvblox-mesh.ply'}" > "$RUN/logs/nvblox-save-ply.log" 2>&1
cat "$RUN/reports/nvblox-output.json"

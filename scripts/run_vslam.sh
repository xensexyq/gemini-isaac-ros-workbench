#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
ROOT=/workspaces/isaac_ros-dev
RUN="${ISAAC_RUN_DIR:-$ROOT/runs/$(date +%Y%m%d-%H%M%S)-vslam}"
mkdir -p "$RUN/logs" "$RUN/reports"
LAUNCH_PID=""
OBSERVER_PID=""
cleanup() {
  if [[ -n "$LAUNCH_PID" ]]; then kill -INT -- "-$LAUNCH_PID" 2>/dev/null || true; wait "$LAUNCH_PID" 2>/dev/null || true; fi
  if [[ -n "$OBSERVER_PID" ]]; then kill "$OBSERVER_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT
setsid ros2 launch isaac_ros_examples isaac_ros_examples.launch.py \
  launch_fragments:=visual_slam \
  interface_specs_file:="$ROOT/assets/isaac_ros_visual_slam/quickstart_interface_specs.json" \
  rectified_images:=false > "$RUN/logs/vslam-launch.log" 2>&1 &
LAUNCH_PID=$!
python3 "$ROOT/scripts/wait_for_topic.py" /left/image_rect --subscribers --timeout 90
python3 "$ROOT/scripts/observe_outputs.py" vslam "$RUN/reports/vslam-output.json" --seconds 35 > "$RUN/logs/vslam-observer.log" 2>&1 &
OBSERVER_PID=$!
sleep 3
ros2 bag play "$ROOT/assets/isaac_ros_visual_slam/quickstart_bag" --rate 0.2 \
  --remap \
  /front_stereo_camera/left/image_raw:=/left/image_rect \
  /front_stereo_camera/left/camera_info:=/left/camera_info_rect \
  /front_stereo_camera/right/image_raw:=/right/image_rect \
  /front_stereo_camera/right/camera_info:=/right/camera_info_rect \
  /back_stereo_camera/left/image_raw:=/rear_left/image_rect \
  /back_stereo_camera/left/camera_info:=/rear_left/camera_info_rect \
  /back_stereo_camera/right/image_raw:=/rear_right/image_rect \
  /back_stereo_camera/right/camera_info:=/rear_right/camera_info_rect \
  > "$RUN/logs/vslam-bag.log" 2>&1
wait "$OBSERVER_PID"
OBSERVER_PID=""
cat "$RUN/reports/vslam-output.json"

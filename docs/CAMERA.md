# Camera operation

[English](CAMERA.md) · [简体中文](CAMERA-zh.md) · [Home](../README.md)

## 1. Connection and container

Connect one Gemini 335L or 336L directly with a USB 3 data cable. Check that its connection reports `5000M` or higher in `lsusb -t`. Record its model, serial and firmware; verify SDK compatibility without automatically flashing firmware.

```bash
./scripts/live.sh doctor
./scripts/live.sh start
./scripts/live.sh exec ros2 run orbbec_camera list_devices_node
```

`start` creates an idle container and does not start a camera. It binds `/dev/bus/usb` and grants character device major 189 read/write access for re-enumeration. Container root accesses the devices without host udev changes. All Linux capabilities are dropped, privilege escalation is disabled, the root filesystem is read-only and networking is disabled. The mapped bus also exposes other USB devices; stop the container when done. Actual access and hotplug behavior still require hardware verification.

## 2. Select a mode

```bash
./scripts/live.sh camera
./scripts/live.sh vslam
./scripts/live.sh mapping
```

Each command stays in the foreground. Stop with Ctrl+C before running the next command; a container-side lock prevents duplicate pipelines. Add a serial number as the final argument when multiple cameras are attached. `./scripts/live.sh stop` removes the idle/live container while retaining images and data.

| Mode | Data and processing |
| --- | --- |
| `camera` | Left/right IR, native depth, automatic-profile color, IMU and camera TF. |
| `vslam` | Stereo visual tracking from left/right IR; IMU is published but not fused. |
| `mapping` | Stereo visual tracking plus native depth geometry, using `odom` TF. |

`config/gemini330.yaml` requests IR `640×480 @30Hz Y8` and depth `640×480 @30Hz Y16`. Check supported profiles on the actual device before accepting these settings. The projector and interleaving are disabled; depth quality depends on scene texture and lighting. Color mapping, projector-interleaved tracking, IMU fusion and GUI forwarding are outside the provided baseline.

Raw IR is passed with its CameraInfo distortion (`rectified_images=false`). The SDK publishes native depth in millimeters after applying its value scale; depth/color alignment is disabled. Verify units, calibration and timestamps on hardware. nvblox's `odom` map is not globally deformed after SLAM loop closure.

## 3. Observe from another terminal

Enter the same container with `./scripts/live.sh shell`. Do not run `shell.sh` to create an unrelated second container. Then run individual checks, stopping continuous commands with Ctrl+C:

```bash
ros2 topic list -t
ros2 topic hz /camera/left_ir/image_raw
ros2 topic hz /camera/right_ir/image_raw
ros2 topic hz /camera/depth/image_raw
ros2 topic hz /camera/gyro_accel/sample
ros2 topic echo /camera/left_ir/camera_info --once
ros2 topic echo /camera/right_ir/camera_info --once
ros2 topic hz /visual_slam/tracking/odometry
ros2 run tf2_ros tf2_echo odom camera_link
```

Depth is enabled only in camera/mapping mode; tracking output exists only in vslam/mapping mode. The driver may publish images only while subscribers are present. First observe a stationary camera, then move and rotate slowly in a well-lit textured scene and return to the starting position. Check stereo pairing, CameraInfo/TF, time continuity, tracking loss, stationary jitter, drift, mesh ghosting, actual latency and GPU memory. Software startup alone does not establish these properties.

## 4. Record and export

Inside the container, use a fresh path for each recording:

```bash
RUN=/workspaces/isaac_ros-dev/runs/live-$(date +%Y%m%d-%H%M%S)
mkdir -p "$RUN"
ros2 bag record --storage mcap -o "$RUN/camera-bag" \
  /camera/left_ir/image_raw /camera/left_ir/camera_info \
  /camera/right_ir/image_raw /camera/right_ir/camera_info \
  /camera/depth/image_raw /camera/depth/camera_info \
  /camera/gyro_accel/sample /tf /tf_static /visual_slam/tracking/odometry
```

Stop recording with Ctrl+C. When mapping has produced a mesh, export from another container terminal:

```bash
OUT=/workspaces/isaac_ros-dev/runs/live-mesh-$(date +%Y%m%d-%H%M%S).ply
ros2 service call /nvblox_node/save_ply nvblox_msgs/srv/FilePath "{file_path: '$OUT'}"
```

Files appear under the checkout's `runs/` directory. Check free disk space before recording. If USB access or a stream fails, keep the error log, stop competing camera programs and the container, and investigate the actual device/profile; the scripts do not silently change host permissions or firmware.

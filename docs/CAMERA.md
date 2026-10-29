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


The container uses `config/fastdds.xml` with a 64 MiB shared-memory segment and a 16 MiB message limit to avoid dropping large images with the small default buffer. `live.sh start` supplies it through `FASTRTPS_DEFAULT_PROFILES_FILE`, verified in the current image. After changing it, run `./scripts/live.sh stop` followed by `./scripts/live.sh start` to recreate the container. No host `/dev/shm`, USB buffer or driver changes are required.

Compare SDK logs, image topics and algorithm outputs when diagnosing frame rates; a configured 30 Hz profile alone is insufficient. Decoded `1280×720 rgb8` color is about 2.64 MiB per frame; `640×480 16UC1` depth is about 600 KiB. An observer can also add load. Record the sampling duration, subscriptions and whether mapping is running concurrently.

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

## 5. Interpret the outputs

- `/visual_slam/tracking/odometry`: camera pose relative to `odom`, suitable for plotting a trajectory. Robot-base or end-effector pose requires additional extrinsics and TF.
- `/nvblox_node/mesh` and exported PLY: a triangle mesh of observed surfaces. Inspect local geometry, holes and ghosting in a PLY viewer. A test may also generate an offline HTML preview, linked from its local `runs/` report. Such previews use height coloring; this pipeline does not fuse camera color.
- `/nvblox_node/static_map_slice`: an ESDF slice for obstacle-distance queries by a planner. This project does not integrate a complete Nav2 navigation stack, robot control or safety stopping.

Initial uses include indoor robot visual localization, local obstacle reconstruction, handheld local scanning and ROS perception-pipeline experiments. A distance field does not automatically produce a feasible path, and a mesh is not a metrology-grade CAD model. With the projector disabled, depth depends on natural texture and lighting; nearby moving people, reflective surfaces and incomplete coverage can leave holes or ghosting. Integration is in `odom`; the map is not globally deformed after a VSLAM loop closure.

Live RViz requires these topics and the corresponding plugins, plus a GUI connection. The current container does not forward the host display server. Export and view PLY first; no host driver changes are needed.

## 6. Live mapping in the browser

From a host terminal in the project:

```bash
./scripts/live.sh start
./scripts/live.sh visualize
# Multiple cameras: ./scripts/live.sh visualize <target-serial>
```

Open `http://127.0.0.1:8770/`. `visualize` starts the camera, VSLAM, nvblox and the viewer. The container pipeline lock prevents two pipelines from opening the camera concurrently. Wait for camera/map initialization and the live status, then translate and rotate slowly with overlapping views of fixed, textured objects. Avoid fast rotations, blank walls and nearby moving people.

The page shows a changing mesh, yellow trajectory, cyan camera outline, odometry rate, data age and update counters. Drag to orbit, scroll to zoom, fit the map or enable camera following. Surfaces are gray by default, with optional height coloring; neither mode is RGB textured. Visualization snapshots are sent at approximately 2 Hz, separately from the approximately 30 Hz odometry/depth inputs.

Press Ctrl+C in the launching terminal to stop, or use another terminal:

```bash
./scripts/live.sh visualize-stop
./scripts/live.sh stop
```

The first command attempts to export the mesh to that run's `reports/live-mesh.ply` before stopping the viewer and its mapping pipeline. It checks PID/process birth time and retains the idle container. Check `ply_export_success` in `reports/bridge-summary.json`; export is not guaranteed without a valid map or when the node has failed. The second removes the idle container. A stopped/stale/disconnected page clearly labels its last retained frame. If another application/container owns the camera, wait for that capture to finish; this entry does not stop other projects.

The viewer binds only host `127.0.0.1` and receives ROS messages through a `docker exec` pipe. The container retains `--network none`; no X11 mount, `xhost`, host ROS or GUI installation is required. The page uses no CDN or external upload. Logs and summaries remain under `runs/<timestamp>-live-view/`, excluded from Git. Display limits are 6000 trajectory points and 500,000 mesh vertices. Invalid/over-budget updates are reported while retaining the last valid map; this does not establish complete coverage.

### 6.1 Demonstration layout and layer meaning

A large 3D view sits beside stacked image panels, with a responsive layout on narrow screens. Toggle the surface, ESDF and reference grid independently; use top/front views, fit, or Shift + drag to pan.

| Layer | Actual input and display meaning |
| --- | --- |
| Gray 3D surface | Incremental nvblox triangle mesh, optionally height-colored; no RGB texture. |
| Rainbow distance field | Observed cells from `/nvblox_node/static_map_slice`; red means distance ≤0 m, purple ≥2 m. Unknown cells are omitted. This is 2D ESDF distance, not floor color or a guarantee of traversability. |
| Color Image | `/camera/color/image_raw`, preserving aspect ratio at up to 640 pixels wide. Viewer mode enables RGB for preview only, without color fusion. |
| Depth Image | `/camera/depth/image_raw`, fixed grayscale range 0.2–5 m, near bright and far dark; invalid depth is black. Native depth and color are not registered. |

The slice uses the message's `origin.z` directly and displays that height. The reference grid is at `odom z=0`; it is not ground detection. Mesh snapshots and both previews update at about 2 Hz and retain capture timestamps. Expired images dim and are labeled; a retained frame is not live capture. ESDF display samples at most 100,000 cells, subsampling larger slices without treating unknown cells as free space.

This reproduces the demonstration's layout and data layers. Full-room coverage, clear texture and robust motion still depend on scanning coverage, valid depth, tracking drift and color fusion. A stationary camera reconstructs only its current view. RGB surface fusion, active/passive emitter interleaving and navigation control are not included.

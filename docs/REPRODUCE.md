# From zero to live mapping

[English](REPRODUCE.md) · [简体中文](REPRODUCE-zh.md) · [Home](../README.md)

## 1. Choose a route

| Available hardware | Route | First observable result |
| --- | --- | --- |
| NVIDIA GPU, no camera | Core image → GPU check → official bags | CUDA result and replay reports |
| One Gemini camera | Core image → camera image → streams → live mapping | Image topics, changing browser mesh and trajectory |
| Existing project images | Verify labels/environment and start at the corresponding check | No need to download every dataset again |

Official VSLAM/nvblox bags are independent checks. Replay success does not establish camera acceptance or joint localization accuracy. Camera mapping does not require downloading both bags.

## 2. Before starting

See [installation](INSTALL.md) for the environment and reference hardware. Clone onto a Linux filesystem with enough space. These commands do not install or modify host software:

```bash
docker version --format '{{.Server.Platform.Name}} {{.Server.Version}}'
nvidia-smi
python3 --version
git --version
df -h .
```

The server platform should be `Docker Engine - Community`, and the NVIDIA driver should identify the GPU. The CUDA Version shown by `nvidia-smi` describes driver capability, not installed host development tools. The next stage checks actual container computation; host ROS/CUDA Toolkit installation is unnecessary.

Machine maintainers must prepare Docker access, Container Toolkit and a compatible driver beforehand. This project does not change host groups, global storage, udev or USB buffers. The checkout and image layers may occupy different filesystems; check space on both.

## 3. Test without a camera

```bash
./scripts/build_image.sh
./scripts/validate_environment.sh gpu
```

Expected: a successful exit, a printed `runs/` path and a GPU report confirming a real CUDA kernel result. On failure, inspect that run before attributing later algorithm startup problems to the camera.

Optional VSLAM replay:

```bash
python3 scripts/prepare.py visual_slam
./scripts/validate_environment.sh vslam
```

Optional nvblox replay (about 9.34 GB compressed, plus extraction space):

```bash
python3 scripts/prepare.py nvblox
./scripts/validate_environment.sh nvblox
```

Expected: pose or nonempty mesh/ESDF evidence under that run. The nvblox check also requests PLY export. Inspect reports, service results and file contents separately. These replays use slowed bag time and do not establish live performance.

## 4. Connect and inspect the camera

```bash
./scripts/build_camera_image.sh
./scripts/validate_camera_setup.sh
./scripts/live.sh doctor
./scripts/live.sh start
./scripts/live.sh exec ros2 run orbbec_camera list_devices_node
./scripts/live.sh camera
```

`validate_camera_setup.sh` does not open a camera and refuses to interrupt an existing live container. End active sessions normally first. Connect one camera using a USB 3 data cable and check for `5000M` or higher in `lsusb -t`. Record model, firmware and serial, and verify supported profiles without automatic firmware updates.

From another terminal, use `./scripts/live.sh shell` to inspect `/camera/left_ir/image_raw`, `/camera/right_ir/image_raw`, `/camera/depth/image_raw` and their CameraInfo in the same container. See the [camera guide](CAMERA.md) for topic/recording commands. An image alone does not establish valid depth; inspect coverage, calibration and timestamps too.

Stop `camera` with Ctrl+C before the next stage. Run only one pipeline; other applications/containers must not exclusively use the same device. With multiple cameras, append the target serial to `camera`, `vslam`, `mapping` or `visualize`. A single camera can omit it; unspecified serials are not passed as empty ROS launch arguments.

## 5. Map, view and save

Run in the host terminal:

```bash
./scripts/live.sh visualize
```

Open **http://127.0.0.1:8770/**, not the `viewer/live.html` file; no additional web server is needed. Wait for live status, odometry rate and mesh vertices. Initial mesh generation takes some initialization time.

Move slowly through normally lit, textured views of fixed objects with overlap between adjacent views. Avoid fast rotations and nearby moving people dominating the image. Fit the map to reframe it; camera following changes the view center. Yellow is the trajectory, cyan the camera, and surface coloring represents height. Input/odometry rate differs from the approximately 2 Hz browser snapshot rate.

Press Ctrl+C to finish, or use another terminal:

```bash
./scripts/live.sh visualize-stop
./scripts/live.sh stop
```

Normal shutdown attempts PLY export before releasing the camera. Inspect the printed run directory:

| File | Purpose |
| --- | --- |
| `logs/mapping.log` | Camera, cuVSLAM and nvblox startup/runtime output |
| `logs/bridge-stderr.log` | ROS viewer bridge errors |
| `reports/bridge-summary.json` | Rates, counters, errors and `ply_export_success` |
| `reports/live-mesh.ply` | Geometry when export succeeds |
| `reports/viewer-final.json` | Final viewer status |

Confirm `ply_export_success=true` and a nonempty file. Export is not guaranteed after abrupt shutdown, device failure or before a valid map exists. `runs/` is excluded from Git; review scene images, maps and device identity separately before sharing.

## 6. Troubleshoot by symptom

| Symptom | Check |
| --- | --- |
| Docker version rejected | Server Platform.Name must be Community, not Docker Desktop |
| Build download failure | Check upstream connectivity/space; retain `.part` files and preserve modified driver sources |
| Device enumerates but `uvc_open`/BUSY fails | Check other terminals, recorders and containers; end competing capture normally |
| Page reports a capture error | Read the detailed reason and that run's `logs/mapping.log`; an HTTP service does not prove camera startup |
| ROS rejects empty `serial_number:=` | Omit the launch argument for one camera or provide an actual target serial |
| Page disconnected/stale | Check whether the launching terminal/container stopped; the retained frame is not live |
| Port `8770` busy | Use this project's `visualize-stop`; do not kill unrelated port owners |
| Image rate below configured rate | Check USB 3, competing capture and `FASTRTPS_DEFAULT_PROFILES_FILE`; recreate the container after configuration changes |
| Holes or ghosting | Check valid depth, lighting, texture, motion speed and moving objects; projector-disabled geometry does not guarantee a complete room |
| No PLY after stopping | Inspect `ply_export_success`/`export_error`, confirm a valid mesh existed and stop normally with visualize-stop |

A working local pipeline does not guarantee accuracy/stability on another GPU, firmware or camera model. When sharing reproduction results, record device/firmware, image, mode, scene, duration and actual limits.

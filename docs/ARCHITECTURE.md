# Architecture and workflows

[English](ARCHITECTURE.md) · [简体中文](ARCHITECTURE-zh.md) · [Home](../README.md)

## 1. System boundary

The project is a container workbench, not a new SLAM implementation. Python and shell entry points prepare dependencies, build images, manage containers and observe ROS outputs. OrbbecSDK_ROS2, cuVSLAM and nvblox perform device capture, tracking and reconstruction inside the container. The host supplies Docker Community, the NVIDIA driver and USB devices.

![Overview](assets/architecture-en.svg)

## 2. Entry points and cooperation

| Entry | Main path |
| --- | --- |
| `scripts/build_image.sh` | Verify/extract example configuration, then build the core image. |
| `scripts/build_camera_image.sh` | Verify the base label, prepare fixed Orbbec files, then compile the driver in the image. |
| `scripts/validate_environment.sh` | Create a camera-free container, read-only mount data, run a CUDA check and selected independent dataset replays. |
| `scripts/live.sh` | Create an idle USB container, explicitly execute one live mode, or stop that container. |
| `scripts/validate_camera_setup.sh` | Refuse an active session, inspect runtime configuration and validate components with the camera disabled. |

Build commands wait for completion. During live operation, `docker exec` stays in the foreground while ROS launch manages separate component-container processes. Topic remappings connect data across those processes; they are not ordinary Python function calls.

## 3. Live data contract

`orbbec_live.launch.py` creates the camera component only when `start_camera=true`. The selected mode controls depth/color enablement. Stereo visual tracking consumes `/camera/left_ir/image_raw`, `/camera/right_ir/image_raw` and each stream's `camera_info`. The base frame is `camera_link`; optical frames are `camera_left_ir_optical_frame` and `camera_right_ir_optical_frame`.

Mapping consumes `/camera/depth/image_raw` and `/camera/depth/camera_info`, with transforms in `odom`. It does not fuse IMU or color. Projector interleaving is disabled, so no emitter-frame splitter is present. Independent nvblox sample replay uses the recorded poses/TF; it does not consume the other sample's VSLAM output.

## 4. Lifetimes and failures

- Downloaded files live in ignored cache/input directories. Network attempts are bounded; interrupted parts are retained. Checksums gate completed files. Modified driver/example inputs cause an error and are preserved.
- Docker images outlive containers. The project does not move global storage or prune unrelated images.
- `start` creates an idle `sleep` process. A label protects unrelated containers, and `flock --nonblock` rejects duplicate live pipelines. `stop` removes the container; recordings remain local.
- A validation run owns its output directory and process/container cleanup. Results have no automatic expiry. Observe JSON, service responses and exported geometry separately.

There is no automatic firmware update, host permission rewrite or recovery controller. USB faults, unavailable profiles, invalid calibration and tracking quality require device-specific diagnosis.

## 5. Interactive source map

Open [index.html](architecture/index.html) directly after cloning. It is self-contained and needs no server, build or CDN. Its Chinese interface supports zoom/pan, module expansion, source evidence, object lifetimes and four selectable workflows: build, dataset replay, live mapping and camera-disabled validation.

[architecture.json](architecture/architecture.json) is the editable model. It records the inspected snapshot and exact source locations. A `confirmed` label establishes a source-level configuration/call, not successful hardware operation. Camera access, synchronization, accuracy, real-time behavior and mutable APT dependencies remain visible uncertainties.

For map updates and checks, see [maintenance](DEVELOPMENT.md).

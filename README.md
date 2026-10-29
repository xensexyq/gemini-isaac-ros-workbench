<div align="center">
<h1>Gemini Isaac ROS Workbench</h1>
<p>A Docker Community workbench for Orbbec Gemini cameras, Isaac ROS visual SLAM and depth mapping.</p>

[English](README.md) · [简体中文](README-zh.md)

[Features](#features) · [Architecture](#architecture) · [Quick start](#quick-start) · [Documentation](#documentation)
</div>

<a id="features"></a>
## 1. Features

- Run Isaac ROS 4.6 / ROS 2 Jazzy in Docker Engine Community, keeping ROS and CUDA development packages inside the container.
- Prepare versioned inputs with SHA-256 verification; run a CUDA kernel check and official VSLAM / nvblox dataset replays.
- Bring up Gemini 335L / 336L through separate camera, stereo visual odometry and depth mapping modes.
- Inspect real entry points, data paths and failure branches in an offline interactive architecture map.

Camera profiles are a starting configuration that requires device verification. The live baseline uses stereo vision without IMU fusion, disables the projector and builds geometry without color. It is not a navigation stack or a performance benchmark.

## 2. Components

<table>
<thead><tr><th scope="col">Component</th><th scope="col" width="10000">Responsibility</th></tr></thead>
<tbody>
<tr><td nowrap><a href="scripts/prepare.py">Input prep</a></td><td>Fetch pinned upstream inputs, verify checksums and preserve modified driver sources.</td></tr>
<tr><td nowrap><a href="docker/">Images</a></td><td>Define core and Orbbec-enabled images; downloaded SDK binaries stay outside Git.</td></tr>
<tr><td nowrap><a href="scripts/live.sh">Live container</a></td><td>Manage one USB-enabled container and explicitly start a selected live mode.</td></tr>
<tr><td nowrap><a href="docs/DEVELOPMENT.md">Checks</a></td><td>Check GPU computation, dataset outputs and camera-disabled component startup; write local reports.</td></tr>
</tbody>
</table>

<a id="architecture"></a>
## 3. Architecture

![Build, live camera and independent dataset replay flows](docs/assets/architecture-en.svg)

The live chain connects left/right IR to cuVSLAM, then combines its `odom` TF with native depth in nvblox. Official VSLAM and nvblox replay checks are independent; the nvblox sample provides its own poses and TF.

[Architecture guide](docs/ARCHITECTURE.md) · [Interactive map HTML](docs/architecture/index.html) · [Editable map data](docs/architecture/architecture.json)

Open the HTML after cloning; GitHub displays its source rather than running the map. The interactive map interface is in Chinese.

## 4. Installation

Use an Ubuntu 24.04 x86_64 Linux workstation with Docker Engine Community, a working NVIDIA driver compatible with the container's CUDA 13.2 runtime, and NVIDIA Container Toolkit already configured. Host utilities: Git, Python 3.12+ and `dpkg-deb`; `lsusb` helps diagnose camera connections. Reserve around 80 GB for a fresh build and both datasets, or start with GPU checks only.

This project does not install host packages, update drivers, install udev rules or change global Docker storage. Docker's existing storage location determines where image layers are kept.

```bash
git clone https://github.com/xensexyq/gemini-isaac-ros-workbench.git
cd gemini-isaac-ros-workbench
./scripts/build_image.sh
```

[Installation and dependency details](docs/INSTALL.md)

<a id="quick-start"></a>
## 5. Quick start

First check GPU computation without a camera or dataset download:

```bash
./scripts/validate_environment.sh gpu
```

For a VSLAM dataset replay:

```bash
python3 scripts/prepare.py visual_slam
./scripts/validate_environment.sh vslam
```

Prepare the camera image and verify its components without starting a camera:

```bash
./scripts/build_camera_image.sh
./scripts/validate_camera_setup.sh
```

After connecting one camera through USB 3:

```bash
./scripts/live.sh doctor
./scripts/live.sh start
./scripts/live.sh camera
# Stop the foreground mode with Ctrl+C before switching.
./scripts/live.sh vslam
./scripts/live.sh mapping
```

Run one mode at a time. Supply a camera serial number when multiple devices are attached. Stop the container with `./scripts/live.sh stop`. The container can access the mapped USB bus; see the [camera guide](docs/CAMERA.md) before use.

<a id="documentation"></a>
## 6. Documentation

- [Installation](docs/INSTALL.md): prerequisites, fixed inputs, downloads and storage.
- [Camera operation](docs/CAMERA.md): profiles, topics, recording, mapping and operating limits.
- [Architecture](docs/ARCHITECTURE.md): source responsibilities, object lifetimes and error handling.
- [Maintenance](docs/DEVELOPMENT.md): source checks, container checks and map maintenance.

## 7. Attribution and licensing

Inspired by [orbbec/isaac_ros-dev](https://github.com/orbbec/isaac_ros-dev), using [NVIDIA Isaac ROS](https://nvidia-isaac-ros.github.io/) and [OrbbecSDK_ROS2](https://github.com/orbbec/OrbbecSDK_ROS2). This is an independent integration project.

Project-authored code does not currently have a blanket license grant. Third-party components retain their own licenses; see [NOTICE](NOTICE) and the preserved [Apache-2.0 text](LICENSES/Apache-2.0.txt). Container images, SDK binaries and datasets are downloaded from upstream rather than redistributed here.

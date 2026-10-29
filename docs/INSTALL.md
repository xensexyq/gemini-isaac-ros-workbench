# Installation

[English](INSTALL.md) · [简体中文](INSTALL-zh.md) · [Home](../README.md)

## 1. Prerequisites

Ubuntu 24.04 x86_64, Python 3.12+, Git and `dpkg-deb` are the host tools. Docker must identify itself as `Docker Engine - Community`; Docker Desktop is not used. Configure NVIDIA Container Toolkit and a driver compatible with CUDA 13.2 before running this project. No setup command here installs or modifies host drivers, udev rules, ROS, software sources or the Docker daemon.

Keep the checkout on a Linux filesystem such as ext4. Container image storage follows the existing Docker/containerd configuration; moving the checkout alone does not move image layers. Around 80 GB of free storage is recommended for a fresh build plus both datasets. The nvblox archive alone is about 9.34 GB, with additional extracted data and Docker build cache.


### 1.1 Reference environment and support boundary

| Item | Local reference |
| --- | --- |
| OS / GPU | Ubuntu 24.04 x86_64 / RTX 5060 Laptop, 8 GB VRAM |
| Driver / container | NVIDIA 595.99.02 / Docker Engine Community 29.7.1 |
| Algorithms / ROS | Isaac ROS 4.6 / ROS 2 Jazzy, container CUDA 13.2 |
| Camera / wrapper | Gemini 335L, firmware 1.2.81 / OrbbecSDK_ROS2 2.10.6 |
| Candidate hardware | Gemini 336L uses the same-family configuration and still needs hardware acceptance |

This is a working reference, not a universal GPU/driver/firmware compatibility list or minimum-version promise. The live container defaults to 20 GiB RAM, 12 CPUs and 2 GiB `/dev/shm` limits; check host resources. Browser visualization needs WebGL 2. Its host relay uses only Python's standard library, without host ROS, a web framework or X11 components.

## 2. Build images

```bash
./scripts/build_image.sh
./scripts/build_camera_image.sh
```

The first command prepares the small official example package and builds `gemini-isaac-ros:4.6-jazzy`. The second prepares Orbbec sources and builds `gemini-isaac-ros:4.6-jazzy-camera-v2.10.6`. Both reuse Docker's build cache and do not push images to a registry.

`config/dependencies.lock.json` pins the NVIDIA base digest, Orbbec revision, example package and dataset checksums. The driver file manifest is `docker/orbbec-source-manifest.json`. APT dependencies resolve from upstream repositories at build time, so these pins do not guarantee byte-identical rebuilds.

The example package is verified and extracted to supply launch/configuration files; it is not recorded as an installed APT package. Core binaries are installed with APT inside the image, without the unused people inference stack.

## 3. Prepare optional data

```bash
python3 scripts/prepare.py visual_slam
python3 scripts/prepare.py nvblox
```

Downloads come from official NVIDIA NGC resources and require network access and applicable upstream terms. Interrupted transfers retain `.part` files; completed files must match pinned byte counts and SHA-256 before extraction. Extraction uses Python's data filter and checks available space. Prepared metadata markers avoid repeated extraction; they are not a full audit of manually edited bag files.

`python3 scripts/prepare.py all` prepares all dependencies and both datasets. Prefer separate targets if storage is limited. Driver sources and extracted example configuration are verified on reuse; modified source files are preserved and cause an error instead of being overwritten.

## 4. Local storage

| Directory | Contents |
| --- | --- |
| `.cache/` | Downloaded inputs, partial transfers and preparation markers. |
| `docker/orbbec-src/` | Downloaded driver sources, original notices and x64 SDK libraries. |
| `docker/official-examples/` | Extracted official example configuration. |
| `assets/` | Extracted datasets. |
| `runs/` | Reports, logs, recorded bags and exported meshes. |

These directories are excluded from Git. Removing a downloaded archive can save space after verifying extraction, but keep its preparation marker to reuse extracted data. Do not remove files during an active build or recording.

Next: [camera operation](CAMERA.md) or [maintenance checks](DEVELOPMENT.md).

# Maintenance and checks

[English](DEVELOPMENT.md) · [简体中文](DEVELOPMENT-zh.md) · [Home](../README.md)

## 1. Source checks

```bash
python3 -B -m unittest discover -s tests -v
for f in scripts/*.sh docker/camera-entrypoint.sh; do bash -n "$f"; done
```

Tests exercise dependency integrity, partial-transfer recovery, changed-source preservation and archive path boundaries. They do not require ROS, Docker, a GPU or a camera, and do not substitute for runtime validation.


Viewer checks also cover incremental mesh replacement/deletion, atomic invalid-data rejection, ESDF coordinates/unknown cells, read-only HTTP and stop-process identity. Image encoding tests need container NumPy/OpenCV and explicitly skip when unavailable on the host. In an existing idle container run `./scripts/live.sh exec python3 -m unittest discover -s /workspaces/isaac_ros-dev/tests -p test_live_images.py -v`.

## 2. Container checks

```bash
./scripts/validate_environment.sh gpu
./scripts/validate_camera_setup.sh
```

The second command checks the driver and container policy, executes a CUDA kernel and starts VSLAM/nvblox with `start_camera=false`. It refuses to reuse an existing live container. No camera is opened.

Prepare optional data with `scripts/prepare.py` before replay checks:

```bash
./scripts/validate_environment.sh vslam
./scripts/validate_environment.sh nvblox
# Or run both:
./scripts/validate_environment.sh all
```

Each run saves logs and reports under `runs/`. To reuse data on another disk, set `ISAAC_ASSETS_DIR` to the absolute directory containing `isaac_ros_visual_slam/` and `isaac_ros_nvblox/`; it is mounted read-only. Confirm image identity and review actual output, service responses and PLY contents. A valid sample replay is not a real-time accuracy measurement.

## 3. Architecture maintenance

Edit `docs/architecture/architecture.json` only after tracing changed entry points. Refresh evidence lines, relationships, scenarios, uncertainties and snapshot identity together. If arch-flow is available, regenerate with its actual local helper:

```bash
python3 -B /path/to/arch-flow/scripts/build_map.py \
  docs/architecture/architecture.json --repo . \
  --output docs/architecture --force
```

Replace `/path/to/arch-flow` with the installed skill path. The helper is a maintainer tool, not an application dependency. Open the regenerated HTML and check zoom, pan, reset, expansion, evidence, scenario boundaries and highlighting. Keep the English/Chinese static overviews consistent with the model.

## 4. Changes and publication

Keep downloaded SDKs, assets, cache, recordings and reports outside Git. Preserve upstream notices. Update both language versions when changing usage or capabilities. Check links and rendered README layout in addition to source syntax; publish only the reviewed source snapshot. This repository has no automatic release or image-push workflow.

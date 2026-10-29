# Mapping profiles and persistence

[English](MAPPING.md) · [简体中文](MAPPING-zh.md)

## 1. Choose a profile

This is a functional port to Ubuntu 24.04 / Isaac ROS 4.6 / x86_64, not a reproduction of Jetson / Humble / Isaac ROS 3.0 platform performance or video quality. Room coverage, revisits and dynamic scenes require physical scanning validation.

| Profile | Inputs and outputs | Purpose |
| --- | --- | --- |
| `baseline` (default) | Emitter off; 30 FPS stereo VO; local TSDF/ESDF without color fusion | Basic camera, localization and pipeline diagnosis |
| `original` | Synchronized 60 FPS RGB/depth/IR; metadata routes emitter-off IR and emitter-on depth; colored dynamic nvblox in `odom` | Upstream combined-example behavior; global SLAM disabled, 7 m local clearing radius |
| `persistent` | Same routing; colored static nvblox without distance clearing or decay; global SLAM; separate CPU global surface map | Retain coverage and rebuild historical surfaces from optimized poses |
| `vio` command | 30 FPS emitter-off stereo and synchronized IMU; visual-inertial poses | Standalone localization example; no nvblox |

`original` and `persistent` require the derived camera image. Its patch exposes the SDK `OB_PROP_LASER_ON_OFF_PATTERN_INT` property (formerly `OB_PROP_LASER_ON_OFF_MODE_INT`), setting and reading it at startup without firmware updates or save-settings calls. Baseline explicitly resets it to zero. Routing uses each frame's `frame_emitter_mode`; missing or invalid metadata is dropped, never guessed from frame parity. The configuration references a 335L; other firmware and the 336L need profile and metadata validation.

## 2. Start and inspect

```bash
./scripts/build_camera_image.sh
./scripts/live.sh start
GEMINI_PROFILE=original ./scripts/live.sh visualize
# Stop the previous pipeline before enabling retention and global correction:
GEMINI_PROFILE=persistent ./scripts/live.sh visualize
# Standalone VIO, after stopping the previous capture:
./scripts/live.sh vio
```

Capture entry points share one pipeline lock. Stop the viewer with Ctrl+C or `./scripts/live.sh visualize-stop` in another terminal. The [local page](http://127.0.0.1:8770/) offers:

- **Local nvblox**: colored surfaces, trajectory, RGB/depth and a real ESDF slice; `original` displays the combined static/dynamic distance field. The reference grid is not detected ground; distance colors are not surface colors.
- **Global correction**: historical keyframe surfaces in the independent `map` frame. Local `odom` ESDF/trajectory are hidden to prevent frame mixing. Status shows keyframes, rebuild progress, historical pose changes and capacity errors.
- **Surface boundaries**: cyan open edges of observed surfaces, including depth holes and scan edges. Walls and obstacles must be observed. These edges are not automatically extracted room outlines, virtual fences or navigation safety boundaries. Unobserved space stays unknown.

Stationary operation only checks streams, updates and interfaces. Scan slowly with overlapping views, then revisit textured static areas from similar viewpoints. Moving people, blank walls, glass and rapid motion can degrade localization; revisiting a point does not guarantee loop closure.

## 3. Correcting historical geometry

`persistent` queries cuVSLAM `GetAllPoses` for optimized historical poses. It interpolates odometry at the original depth timestamp, associates a SLAM anchor within 50 ms and applies calibrated extrinsics. It never substitutes latest TF for historical pose. Each keyframe retains its local surface and anchor-relative transform.

When an existing anchor changes by more than 5 mm or 0.2°, all retained keyframes are reprojected and fused. The complete new revision replaces the previous geometry atomically in the viewer. The counter measures historical pose updates, **not confirmed loop closures**. This module does not reintegrate the local nvblox TSDF. The global map is separate CPU surface fusion, with an 8-pixel depth sampling stride and 4 cm vertex voxel fusion; it is not a second nvblox TSDF and provides no global ESDF.

Keyframes are selected around 10 cm / 8° / 2 seconds, subject to valid poses and image availability. Each session is limited to 600 frames and 512 MiB of uncompressed keyframe data; acquisition pauses below 1 GiB free disk. Global geometry is limited to 500,000 vertices and 1,000,000 triangles. The pose query limit is 60,000; start a new session when reached. Limits retain existing geometry and report errors rather than silently deleting old regions. Moving objects can leave traces in the global static surface map.

## 4. Save, recover and inspect offline

Normal shutdown attempts to export local `reports/live-mesh.ply`. `persistent` also saves:

- `global/keyframe-*.npz`: local geometry, colors, timestamps and anchor relationships.
- `global/global-state.json`: atomically written complete-revision manifest and optimized poses; recovery uses only listed keyframes.
- `global/global-mesh.json` and `global/global-mesh.ply`: global surfaces.
- `global/slam-map/`: cuVSLAM save-service output; check `slam_map_saved` in the report.
- `reports/viewer-snapshot.json`: final local/global geometry and preview images for offline browsing.

```bash
# No camera or ROS startup; replace with the actual session directory
python3 scripts/live_view.py --replay runs/<session>
# Re-fuse saved keyframes and optimized poses inside the standby container
./scripts/live.sh exec python3 /workspaces/isaac_ros-dev/scripts/rebuild_global.py \
  /workspaces/isaac_ros-dev/runs/<session>/global
```

Offline viewing remains labeled as stopped capture. Snapshots contain the last scene images and belong in local, Git-ignored `runs/`. Offline rebuilding does not perform new loop optimization. Automatic old-SLAM-map loading and fusion across sessions are not implemented.

## 5. Validation limits

Software checks cover exact timestamp routing, invalid metadata, independent historical corrections, replacement of old geometry, depth holes, capacity and recovery. They cannot replace real loop-closure acceptance. Stationary reference-device checks do not establish dynamic obstacle removal, complete room closure, correction accuracy or metrology performance. The upstream video is a visual target, not a guaranteed reproduced result.

See [Development](DEVELOPMENT.md) for checks. References: [Orbbec example](https://github.com/orbbec/isaac_ros-dev), [laser alternating property](https://orbbec.github.io/docs/OrbbecSDKv2/_property_8h.html).

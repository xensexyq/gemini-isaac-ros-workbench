# 相机操作

[English](CAMERA.md) · [简体中文](CAMERA-zh.md) · [首页](../README-zh.md)

## 1. 连接与容器

使用 USB 3 数据线直连一台 Gemini 335L 或 336L，确认 `lsusb -t` 中相机连接显示 `5000M` 或更高。记录型号、序列号和固件，核对 SDK 兼容性，不自动刷写固件。

```bash
./scripts/live.sh doctor
./scripts/live.sh start
./scripts/live.sh exec ros2 run orbbec_camera list_devices_node
```

`start` 只创建待命容器，不启动相机。容器绑定 `/dev/bus/usb`，授予主设备号 189 的字符设备读写权限，以适应重新枚举。使用容器 root 访问设备，不修改宿主 udev。容器移除全部 Linux capabilities、禁止提权，根文件系统只读且不连接网络。映射总线也会暴露其他 USB 设备，使用结束后请停止容器。实际打开设备与热插拔行为仍需实机验证。

## 2. 选择模式

```bash
./scripts/live.sh camera
./scripts/live.sh vslam
./scripts/live.sh mapping
```

各命令在前台运行，按 Ctrl+C 停止后再执行下一条；容器内的锁会阻止重复启动管线。多相机连接时，把目标序列号作为最后一个参数。`./scripts/live.sh stop` 会移除待命或运行容器，保留镜像和数据。

| 模式 | 数据与处理 |
| --- | --- |
| `camera` | 左右红外、原生深度、自动 profile 的彩色、IMU 与相机 TF。 |
| `vslam` | 使用左右红外进行双目视觉跟踪；IMU 仅出流，不融合。 |
| `mapping` | 双目视觉跟踪，加上基于 `odom` TF 的原生深度几何建图。 |

`config/gemini330.yaml` 请求红外 `640×480 @30Hz Y8`、深度 `640×480 @30Hz Y16`。接入时必须核对设备实际支持的 profile。投射器及交替投射关闭，深度质量依赖纹理与光照。当前基线不包含彩色建图、交替投射跟踪、IMU 融合和 GUI 转发。

原始红外图像携带 CameraInfo 畸变参数送入 VSLAM（`rectified_images=false`）。SDK 在应用 value scale 后以毫米发布原生深度，深度和彩色对齐关闭。需要实测单位、标定和时间戳。SLAM 回环后，nvblox 的 `odom` 地图不会整体变形优化。

## 3. 在另一个终端观察

使用 `./scripts/live.sh shell` 进入同一容器，不要用 `shell.sh` 新建另一个无关容器。逐条执行以下检查，持续运行的命令按 Ctrl+C 停止：

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

深度仅在 camera/mapping 模式开启，跟踪输出仅在 vslam/mapping 模式出现。驱动可能仅在存在订阅者时发布图像。先静置观察，再在光照充足、纹理明显的场景缓慢平移、旋转并回到起点。检查双目配对、CameraInfo/TF、时间连续性、跟踪丢失、静止抖动、漂移、网格重影、实际延迟和显存。软件启动成功不能证明这些实机指标。

## 4. 录制与导出

在容器中为每次录制使用新路径：

```bash
RUN=/workspaces/isaac_ros-dev/runs/live-$(date +%Y%m%d-%H%M%S)
mkdir -p "$RUN"
ros2 bag record --storage mcap -o "$RUN/camera-bag" \
  /camera/left_ir/image_raw /camera/left_ir/camera_info \
  /camera/right_ir/image_raw /camera/right_ir/camera_info \
  /camera/depth/image_raw /camera/depth/camera_info \
  /camera/gyro_accel/sample /tf /tf_static /visual_slam/tracking/odometry
```

Ctrl+C 停止录制。mapping 已产生网格时，在另一个容器终端导出：

```bash
OUT=/workspaces/isaac_ros-dev/runs/live-mesh-$(date +%Y%m%d-%H%M%S).ply
ros2 service call /nvblox_node/save_ply nvblox_msgs/srv/FilePath "{file_path: '$OUT'}"
```

文件位于宿主项目的 `runs/` 目录，录制前检查剩余空间。USB 访问或数据流异常时，保留错误日志，停止其他相机程序及本容器后排查实际设备和 profile；脚本不会悄悄修改宿主权限或固件。

# 相机操作

[English](CAMERA.md) · [简体中文](CAMERA-zh.md) · [首页](../README-zh.md)

本指南默认命令使用 `baseline`。交替投射、彩色融合、独立 VIO、历史纠图及保存恢复见[建图模式](MAPPING-zh.md)。

## 1. 连接与容器

使用 USB 3 数据线直连一台 Gemini 335L 或 336L，确认 `lsusb -t` 中相机连接显示 `5000M` 或更高。记录型号、序列号和固件，核对 SDK 兼容性，不自动刷写固件。

```bash
./scripts/live.sh doctor
./scripts/live.sh start
./scripts/live.sh exec ros2 run orbbec_camera list_devices_node
```

`start` 只创建待命容器，不启动相机。容器绑定 `/dev/bus/usb`，授予主设备号 189 的字符设备读写权限，以适应重新枚举。使用容器 root 访问设备，不修改宿主 udev。容器移除全部 Linux capabilities、禁止提权，根文件系统只读且不连接网络。映射总线也会暴露其他 USB 设备，使用结束后请停止容器。Gemini 335L 已验证设备打开；其他型号及 USB 热插拔恢复需分别验证。


容器使用 `config/fastdds.xml` 为 Fast DDS 配置 64 MiB 共享内存段和 16 MiB 消息上限，避免大图像在默认小缓冲下丢帧。`live.sh start` 通过 `FASTRTPS_DEFAULT_PROFILES_FILE` 传入配置；该变量在当前镜像中已验证生效。修改后先 `./scripts/live.sh stop`，再 `./scripts/live.sh start` 重建容器。无需修改宿主 `/dev/shm`、USB 缓冲或驱动。

排查帧率时比较设备 SDK 日志、图像话题和算法输出，不能只看设备配置的 30 Hz。彩色 `1280×720 rgb8` 解码后每帧约 2.64 MiB，深度 `640×480 16UC1` 约 600 KiB。观察节点本身也可能增加负载；记录采样时长、订阅话题和是否同时运行建图。

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

## 5. 看什么结果

- `/visual_slam/tracking/odometry`：相机相对 `odom` 的位姿，可用于绘制轨迹；不等于机器人底盘或机械臂末端位姿，需要额外外参和 TF。
- `/nvblox_node/mesh` 和导出的 PLY：已观测表面的三角网格。用支持 PLY 的三维查看器检查局部形状、空洞与重影；当次测试也可以生成离线 HTML 预览，位置见本地 `runs/` 报告。实时表面默认灰白，可切换高度着色；基线不融合颜色，`original` / `persistent` 使用真实 RGB 颜色。
- `/nvblox_node/static_map_slice`：ESDF 距离场切片，可作为规划器判断障碍物距离的输入；本项目没有接入完整 Nav2 导航、机器人控制或安全停车。

适合先验证室内机器人视觉定位、局部障碍物建图、手持局部扫描和 ROS 感知管线。距离场并不自动得到可行路径，网格也不等于可量测的 CAD 模型。投射器关闭时深度依赖自然纹理和光照；近距离动态人员、反光面和覆盖不足都可能留下空洞或重影。地图在 `odom` 中融合，不会在 VSLAM 回环后自动整体变形优化。

实时 RViz 显示需要相机容器中的话题及对应插件，并额外配置 GUI 连接；当前容器没有转发宿主显示服务。也可使用下方浏览器入口，不需要为此修改宿主驱动。

## 6. 实时建图与浏览器显示

在宿主终端进入项目，执行：

```bash
./scripts/live.sh start
./scripts/live.sh visualize
# 多相机时使用：./scripts/live.sh visualize <目标序列号>
```

浏览器打开 `http://127.0.0.1:8770/`。`visualize` 自动启动相机、VSLAM、nvblox 和实时查看器；管线锁保证同一容器只启动一套相机管线。首次需要等待相机与地图初始化。确认页面显示“实时更新中”后，缓慢平移并转动相机，保持固定、有纹理的场景在视野中，相邻画面保留重叠。避免快速甩动、长时间朝向空白墙或近距离动态人员。

页面显示持续更新的网格、黄色轨迹和青色相机框，以及定位频率、数据年龄和更新编号。拖动旋转、滚轮缩放；“适配地图”重新取景，“跟随相机”将视图中心移到当前相机位置。表面默认灰白，可切换高度着色；均不是 RGB 纹理。地图通常按约 2 Hz 的可视化快照传给网页；这与约 30 Hz 的定位和深度输入频率不同。

停止时，在启动终端按 Ctrl+C；也可以在另一个终端执行：

```bash
./scripts/live.sh visualize-stop
./scripts/live.sh stop
```

第一条先尝试把当前网格导出到当次 `reports/live-mesh.ply`，再停止本项目查看器及其启动的建图管线，使用 PID 和进程启动时间校验，保留待命容器。导出结果见 `reports/bridge-summary.json` 的 `ply_export_success`；没有有效地图或节点异常时不能保证导出。第二条移除待命容器。页面断开或数据过期时会明确提示，最后保留的画面不能当作仍在更新。若同一相机被其他容器或程序占用，应先等待其采集结束；本入口不会停止其他项目的进程。

查看器只监听宿主 `127.0.0.1`，通过 `docker exec` 管道读取容器内 ROS 消息；容器仍为 `--network none`，不挂载 X11、不使用 `xhost`，不安装宿主 ROS 或 GUI 依赖。网页没有 CDN 或外部上传。完整日志和采样摘要保存在 `runs/<时间>-live-view/`，实景数据不进入 Git。显示保留最近最多 6000 个轨迹点，并限制最多 50 万个网格顶点；超限或数据异常会提示错误并保留最后有效地图，不能视作全图完成。

### 6.1 参考演示布局与图层含义

页面采用大幅三维视图和右侧上下图像窗，窄屏自动调整布局。可分别开关表面、ESDF、参考网格，使用俯视/正视、适配地图或 Shift + 拖动平移。

| 图层 | 真实输入与显示含义 |
| --- | --- |
| 灰白三维表面 | nvblox 增量三角网格；可切换高度色，不包含 RGB 纹理。 |
| 彩虹距离场 | `/nvblox_node/static_map_slice` 的观测单元；红色为距离 ≤0 m，紫色为 ≥2 m，未知区域不绘制。距离是二维 ESDF，不是地面颜色或可行驶保证。 |
| Color Image | `/camera/color/image_raw`，按原始图像比例缩小至最多 640 像素宽；仅在查看器模式额外启用 RGB，不开启颜色融合。 |
| Depth Image | `/camera/depth/image_raw`，固定 0.2–5 m 灰度显示，近亮远暗，无效深度为黑色。基线原生深度未对齐；交替模式使用软件对齐深度。 |

切片位置直接使用消息的 `origin.z`，页面显示实际高度；参考网格位于 `odom z=0`，不表示自动检测到了地面。三维快照和两幅图像约 2 Hz，保留采集时间戳；图像过期会变暗并标注，不能用末帧判断实时出流。ESDF 显示最多 10 万个采样单元，大切片抽样显示，未知值不会被填成自由空间。

这是演示的布局和数据层级。完整房间、清晰纹理和稳健运动效果还取决于扫描覆盖、深度有效率、定位漂移与颜色融合；静置只生成当前视野的局部几何。当前不包含 RGB 表面融合、主动/被动投射交替或导航控制。

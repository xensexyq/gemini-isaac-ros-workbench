# 从零到实时建图

[English](REPRODUCE.md) · [简体中文](REPRODUCE-zh.md) · [首页](../README-zh.md)

## 1. 选择测试路线

| 手头条件 | 建议路线 | 第一项可观察结果 |
| --- | --- | --- |
| NVIDIA GPU，没有相机 | 核心镜像 → GPU 检查 → 官方录包 | CUDA 计算结果和录包输出报告 |
| 一台 Gemini 相机 | 核心镜像 → 相机镜像 → 出流 → 实时建图 | 图像话题、网页中增长的网格与轨迹 |
| 已有本项目镜像 | 检查标签与环境后直接从对应验证阶段开始 | 不需要重复下载所有数据 |

官方 VSLAM 与 nvblox 录包是独立测试；通过回放不等于相机或联合定位精度通过。相机建图不需要先下载两套录包。

## 2. 开始前检查

环境和参考设备见[安装指南](INSTALL-zh.md)。在可用空间充足的 Linux 文件系统中克隆项目。以下命令不安装或修改宿主软件：

```bash
docker version --format '{{.Server.Platform.Name}} {{.Server.Version}}'
nvidia-smi
python3 --version
git --version
df -h .
```

Docker 服务端应为 `Docker Engine - Community`，NVIDIA 驱动应能正常识别 GPU。`nvidia-smi` 中的 CUDA Version 表示驱动能力，不代表宿主安装了对应开发工具。实际容器计算由下一阶段检查；无需为本项目在宿主安装 ROS 或 CUDA Toolkit。

Docker 权限、Container Toolkit 和兼容驱动应由机器维护者事先准备。项目不会自动调整用户组、全局镜像存储、udev 或 USB 缓冲。项目目录与镜像层可能位于不同分区，两者都需留出空间。

## 3. 无相机测试

```bash
./scripts/build_image.sh
./scripts/validate_environment.sh gpu
```

预期：命令成功退出，终端给出 `runs/` 结果路径，GPU 报告确认实际 CUDA 内核计算。失败时先查看该次报告，不要继续把算法启动失败判断成相机问题。

可选 VSLAM 回放：

```bash
python3 scripts/prepare.py visual_slam
./scripts/validate_environment.sh vslam
```

可选 nvblox 回放（归档约 9.34 GB，另需解压空间）：

```bash
python3 scripts/prepare.py nvblox
./scripts/validate_environment.sh nvblox
```

预期：当次 `runs/` 中记录位姿或非空网格/ESDF；nvblox 还会发起 PLY 导出请求。报告、服务结果和文件内容应分别核验。回放使用降低速度的录包时钟，不能当作实机实时性能结果。

## 4. 相机接入与出流

```bash
./scripts/build_camera_image.sh
./scripts/validate_camera_setup.sh
./scripts/live.sh doctor
./scripts/live.sh start
./scripts/live.sh exec ros2 run orbbec_camera list_devices_node
./scripts/live.sh camera
```

`validate_camera_setup.sh` 不打开相机，且拒绝打断已有实机容器；如有正在采集的会话，先正常结束它。用 USB 3 数据线连接一台相机，`lsusb -t` 应显示 `5000M` 或更高。记录型号、固件、序列号，确认 profile 支持；不自动升级固件。

另一个终端运行 `./scripts/live.sh shell`，在同一容器中检查 `/camera/left_ir/image_raw`、`/camera/right_ir/image_raw`、`/camera/depth/image_raw` 及其 CameraInfo。话题和录包命令见[相机指南](CAMERA-zh.md)。看到图像不等于深度有效，需同时观察深度覆盖、标定和时间戳。

按 Ctrl+C 结束 `camera` 模式，再开始下一阶段。每次只运行一种管线；其他程序或其他容器也不能同时独占同一相机。多设备连接时为 `camera`、`vslam`、`mapping` 或 `visualize` 追加目标序列号；单设备可不指定，未指定时不向 ROS launch 传空参数。

## 5. 实时建图、查看与保存

在宿主终端运行：

```bash
./scripts/live.sh visualize
```

浏览器打开 **http://127.0.0.1:8770/**，无需打开 `viewer/live.html` 文件，也无需启动其他网页服务器。等待“实时更新中”、定位频率和网格顶点数出现；首次生成网格需要初始化时间。

缓慢移动相机，保持光照正常、有纹理的固定物体在视野中。相邻视野保持重叠，避免快速转身和近距离动态人员占满画面。点击“适配地图”重新取景；“跟随相机”改变观察中心，黄色线为轨迹，青色框为相机，表面颜色仅表示高度。定位输入频率与约 2 Hz 的网页快照频率不同。

结束时按 Ctrl+C，或在另一个终端运行：

```bash
./scripts/live.sh visualize-stop
./scripts/live.sh stop
```

正常停止先尝试导出 PLY，再释放相机。查看终端显示的当次目录：

| 文件 | 用途 |
| --- | --- |
| `logs/mapping.log` | 相机、cuVSLAM 和 nvblox 启动/运行日志 |
| `logs/bridge-stderr.log` | 查看器 ROS 桥接错误 |
| `reports/bridge-summary.json` | 帧率、更新计数、错误及 `ply_export_success` |
| `reports/live-mesh.ply` | 导出成功时的几何网格 |
| `reports/viewer-final.json` | 查看器结束状态 |

`ply_export_success=true` 且文件非空才表示导出成功。异常断电、相机故障或尚无地图时不能保证导出。`runs/` 不进入 Git；分享给其他人前，应单独审查实景图片、地图和设备身份。

## 6. 按现象排查

| 现象 | 检查顺序 |
| --- | --- |
| Docker 版本被拒绝 | 检查服务端 Platform.Name；需要 Community，非 Docker Desktop |
| 镜像构建下载失败 | 检查上游网络和空间；保留 `.part` 后重试，不覆盖已修改驱动源码 |
| 相机枚举正常但打不开、`uvc_open`/BUSY | 查看其他终端、录制工具和容器是否占用；正常结束占用程序后重试 |
| 页面“采集异常” | 先看页面详细原因和当次 `logs/mapping.log`；服务存在不代表相机已启动 |
| ROS 报空的 `serial_number:=` | 不要手动传空 launch 参数；单相机省略它，多相机填实际序列号 |
| 页面断开或数据过期 | 检查启动终端是否退出、容器是否停止；最后画面不会继续采集 |
| `8770` 端口被占用 | 先执行本项目 `visualize-stop`；不要盲目终止其他项目的端口进程 |
| 图像帧率低于设备配置 | 检查 USB 3、同设备占用及 `FASTRTPS_DEFAULT_PROFILES_FILE`；修改容器配置后重新 start |
| 网格有空洞或重影 | 检查深度有效比例、照明、纹理、运动速度和动态物体；当前投射器关闭，不保证完整房间重建 |
| 停止后没有 PLY | 先看 `ply_export_success`/`export_error`，确认停止前已有有效网格，且按 visualize-stop 正常结束 |

本机功能链路通过不等于其他 GPU、固件或相机型号的精度/稳定性保证。发布复现结果时，记录设备/固件、镜像、运行模式、场景、采样时长和实际限制。

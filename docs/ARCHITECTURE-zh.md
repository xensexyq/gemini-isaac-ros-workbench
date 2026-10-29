# 架构与运行流程

[English](ARCHITECTURE.md) · [简体中文](ARCHITECTURE-zh.md) · [首页](../README-zh.md)

以下总览及交互源码图描述默认基线链路。可选模式增加 `emitter_splitter.py` 的精确元数据分流、`global_mapping.py` 的独立历史表面融合与 `rebuild_global.py` 的离线恢复；完整数据语义见[建图指南](MAPPING-zh.md)。

## 1. 系统边界

本项目是容器工作台，不是新的 SLAM 算法实现。Python 和 Shell 入口负责依赖准备、镜像构建、容器管理及 ROS 输出观察。OrbbecSDK_ROS2、cuVSLAM 和 nvblox 在容器中完成采集、跟踪和重建。宿主提供 Docker 社区版、NVIDIA 驱动和 USB 设备。

![架构总览](assets/architecture-zh.svg)

## 2. 入口与协作

| 入口 | 主路径 |
| --- | --- |
| `scripts/build_image.sh` | 校验并提取样例配置，再构建核心镜像。 |
| `scripts/build_camera_image.sh` | 检查基础镜像标签，准备固定 Orbbec 文件，在镜像中编译驱动。 |
| `scripts/validate_environment.sh` | 创建无相机容器，只读映射数据，执行 CUDA 检查及所选的独立数据回放。 |
| `scripts/live.sh` | 创建 USB 待命容器，显式运行一种实机模式，或停止该容器。 |
| `scripts/validate_camera_setup.sh` | 拒绝打断已有会话，检查运行配置并禁用相机验证组件。 |

构建命令同步等待完成。实机运行时，`docker exec` 保持前台，ROS launch 管理多个独立的组件容器进程。话题重映射连接跨进程的数据流，不是普通 Python 函数调用。

## 3. 实机数据契约

`orbbec_live.launch.py` 只在 `start_camera=true` 时创建相机组件，按模式决定是否开启深度和彩色。双目视觉跟踪订阅 `/camera/left_ir/image_raw`、`/camera/right_ir/image_raw` 及各自的 `camera_info`。基座坐标系为 `camera_link`，光学坐标系为 `camera_left_ir_optical_frame` 和 `camera_right_ir_optical_frame`。

建图消费 `/camera/depth/image_raw` 与 `/camera/depth/camera_info`，在 `odom` 中查询变换。基线不融合 IMU 或颜色，也不启用投射器帧分流。独立的 nvblox 样例回放使用录包位姿/TF，不消费另一套样例的 VSLAM 输出。

## 4. 生命周期与失败处理

- 下载文件位于被 Git 忽略的缓存与输入目录。网络尝试有上限，中断分段保留，完整文件通过校验值后才发布。已修改的驱动或样例输入会被保留并报错。
- 镜像生命周期长于容器。本项目不迁移全局存储，也不清理无关镜像。
- `start` 创建 `sleep` 待命进程。标签保护无关容器，`flock --nonblock` 拒绝重复实机管线。`stop` 移除容器，录制文件继续保留。
- 每次验证管理自己的结果目录和进程/容器清理。结果没有自动过期策略。JSON 观察结果、服务返回和导出几何需要分别确认。

项目没有自动刷固件、改写宿主权限或故障恢复控制器。USB 故障、不支持的 profile、错误标定和跟踪质量，需要针对设备排查。

## 5. 交互源码地图

克隆后直接打开 [index.html](architecture/index.html)。它是自包含文件，不需要服务、构建或 CDN。中文界面支持缩放/平移、模块展开、源码证据、对象生命周期，以及构建、数据回放、实机建图、禁用相机验证及浏览器实时查看五种流程。

[architecture.json](architecture/architecture.json) 是可编辑模型，记录检查快照与准确源码位置。`confirmed` 仅表示源码可确认配置或调用，不表示硬件运行成功。相机访问、同步、精度、实时行为和可变 APT 依赖都保留为可见的不确定项。

地图更新与检查方法见[维护指南](DEVELOPMENT-zh.md)。

## 6. 浏览器实时链路

`live.sh visualize` 在宿主启动 `live_view.py`，检查容器归属和 Docker Community，并先绑定回环端口。随后通过 `docker exec` 管道启动容器内 `live_view_bridge.py`；桥接持有管线锁并创建 mapping 子进程，额外启用 RGB 预览，颜色融合仍关闭。

桥接可靠订阅增量网格，并订阅里程计、状态、ESDF、RGB 和深度。`live_mesh.py` 按块合并网格；`live_layers.py` 保留观测 ESDF 单元和原始图像时间戳，生成有界显示数据。宿主仅缓存最新状态、压缩网格及图层；`viewer/live.html` 从只读 HTTP 接口轮询，WebGL 绘制表面/距离场/轨迹，右侧显示 JPEG 预览。容器网络仍关闭，宿主不安装 ROS。

正常停止先尝试 PLY 导出，再终止本次 ROS 子进程并释放相机。停止入口验证 PID 和进程启动时间，避免误停复用的 PID；已有地图在数据中断时明确标为末帧。更多边界见[相机操作](CAMERA-zh.md#61-参考演示布局与图层含义)。

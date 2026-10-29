<div align="center">
<h1>Gemini Isaac ROS Workbench</h1>
<p>基于 Docker 社区版的 Orbbec Gemini 相机、Isaac ROS 视觉定位与深度建图工作台。</p>

[English](README.md) · [简体中文](README-zh.md)

[特性](#features) · [架构](#architecture) · [快速开始](#quick-start) · [文档](#documentation)
</div>

<a id="features"></a>
## 1. 特性

- 在 Docker Engine Community 中运行 Isaac ROS 4.6 / ROS 2 Jazzy，将 ROS 和 CUDA 开发依赖留在容器内。
- 使用 SHA-256 校验准备固定版本输入，提供 CUDA 内核检查及官方 VSLAM / nvblox 数据集回放。
- 为 Gemini 335L / 336L 提供相机出流、双目视觉里程计、深度建图三种独立启动模式。
- 通过离线交互架构图查看真实入口、数据流及失败分支。

相机 profile 是需要连接设备验证的起始配置。当前实机基线使用双目视觉，不融合 IMU；关闭投射器，生成不带颜色的几何地图。本项目不包含导航栈，也不提供性能基准结论。

## 2. 组件与职责

<table>
<thead><tr><th scope="col">组件</th><th scope="col" width="10000">职责</th></tr></thead>
<tbody>
<tr><td nowrap><code>scripts/prepare.py</code></td><td>获取固定上游输入、校验文件，并保留已修改的驱动源码。</td></tr>
<tr><td nowrap><code>docker/</code></td><td>定义核心镜像和相机镜像；下载的 SDK 二进制不进入 Git。</td></tr>
<tr><td nowrap><code>scripts/live.sh</code></td><td>管理单个 USB 容器，显式启动所选实机模式。</td></tr>
<tr><td nowrap>验证脚本</td><td>检查 GPU 计算、数据集输出及禁用相机的组件启动，将报告保存在本地。</td></tr>
</tbody>
</table>

<a id="architecture"></a>
## 3. 架构与流程

![镜像构建、实时相机及独立数据集回放流程](docs/assets/architecture-zh.svg)

实机链路将左右红外图像交给 cuVSLAM，再把它发布的 `odom` TF 与原生深度交给 nvblox。官方 VSLAM 和 nvblox 回放是两项独立检查；nvblox 样例使用录包自带的位姿和 TF。

[架构说明](docs/ARCHITECTURE-zh.md) · [交互地图 HTML](docs/architecture/index.html) · [可编辑地图数据](docs/architecture/architecture.json)

克隆后直接打开 HTML 即可交互；GitHub 上的 HTML 链接只展示源码。交互地图界面为中文。

## 4. 安装

使用 Ubuntu 24.04 x86_64 Linux 工作站，提前准备 Docker Engine Community、兼容容器 CUDA 13.2 运行时的 NVIDIA 驱动，以及已配置的 NVIDIA Container Toolkit。宿主工具需要 Git、Python 3.12+ 和 `dpkg-deb`，建议有 `lsusb` 便于检查相机。全新构建并准备两套数据时建议预留约 80 GB，也可以先只检查 GPU。

本项目不会安装宿主软件包、更新驱动、安装 udev 规则或修改全局 Docker 存储。镜像层保存在 Docker 已配置的存储位置。

```bash
git clone https://github.com/xensexyq/gemini-isaac-ros-workbench.git
cd gemini-isaac-ros-workbench
./scripts/build_image.sh
```

[安装与依赖详情](docs/INSTALL-zh.md)

<a id="quick-start"></a>
## 5. 快速开始

先检查 GPU 计算，不需要连接相机或下载数据集：

```bash
./scripts/validate_environment.sh gpu
```

回放 VSLAM 数据集：

```bash
python3 scripts/prepare.py visual_slam
./scripts/validate_environment.sh vslam
```

准备相机镜像，并在不启动相机的情况下检查组件：

```bash
./scripts/build_camera_image.sh
./scripts/validate_camera_setup.sh
```

通过 USB 3 连接一台相机后：

```bash
./scripts/live.sh doctor
./scripts/live.sh start
./scripts/live.sh camera
# 按 Ctrl+C 停止当前前台模式，再切换下一种。
./scripts/live.sh vslam
./scripts/live.sh mapping
```

每次只运行一种模式，多设备连接时指定相机序列号。使用结束后执行 `./scripts/live.sh stop`。容器能够访问映射的 USB 总线，使用前请阅读[相机指南](docs/CAMERA-zh.md)。

<a id="documentation"></a>
## 6. 文档

- [安装指南](docs/INSTALL-zh.md)：环境、固定输入、下载与存储。
- [相机操作](docs/CAMERA-zh.md)：profile、话题、录包、建图及使用边界。
- [架构说明](docs/ARCHITECTURE-zh.md)：源码职责、对象生命周期与失败处理。
- [维护指南](docs/DEVELOPMENT-zh.md)：源码检查、容器检查和地图维护。

## 7. 致谢与许可

项目参考 [orbbec/isaac_ros-dev](https://github.com/orbbec/isaac_ros-dev)，使用 [NVIDIA Isaac ROS](https://nvidia-isaac-ros.github.io/) 和 [OrbbecSDK_ROS2](https://github.com/orbbec/OrbbecSDK_ROS2)，属于独立集成项目。

本项目暂未为自有代码授予统一许可。第三方组件保留其原有许可证，见 [NOTICE](NOTICE) 与保留的 [Apache-2.0 文本](LICENSES/Apache-2.0.txt)。容器镜像、SDK 二进制和数据集从上游下载，不在本仓库重新分发。

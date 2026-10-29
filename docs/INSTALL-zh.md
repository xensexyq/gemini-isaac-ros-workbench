# 安装指南

[English](INSTALL.md) · [简体中文](INSTALL-zh.md) · [首页](../README-zh.md)

## 1. 环境要求

宿主需要 Ubuntu 24.04 x86_64、Python 3.12+、Git 和 `dpkg-deb`。Docker 必须识别为 `Docker Engine - Community`，不使用 Docker Desktop。运行前需准备好 NVIDIA Container Toolkit，以及兼容 CUDA 13.2 的驱动。本项目中的准备命令不会安装或修改宿主驱动、udev 规则、ROS、软件源或 Docker 服务。

建议把项目放在 ext4 等 Linux 文件系统。镜像存储沿用 Docker/containerd 的既有配置；仅移动项目目录不会迁移镜像层。全新构建并准备两套数据时建议预留约 80 GB 空间。nvblox 压缩包本身约 9.34 GB，还需要解压数据和 Docker 构建缓存空间。


### 1.1 参考环境与支持边界

| 项目 | 本机参考配置 |
| --- | --- |
| 系统 / GPU | Ubuntu 24.04 x86_64 / RTX 5060 Laptop，8 GB 显存 |
| 驱动 / 容器 | NVIDIA 595.99.02 / Docker Engine Community 29.7.1 |
| 算法 / ROS | Isaac ROS 4.6 / ROS 2 Jazzy，容器 CUDA 13.2 |
| 相机 / 驱动 | Gemini 335L，固件 1.2.81 / OrbbecSDK_ROS2 2.10.6 |
| 候选设备 | Gemini 336L 使用同系列配置，尚需本机型实测 |

这是可参考的已运行环境，不是所有 GPU、驱动、固件的兼容性列表或最低版本承诺。默认实机容器限制 20 GiB RAM、12 CPU、2 GiB `/dev/shm`；应确认主机资源充足。浏览器实时查看需要 WebGL 2，宿主只使用 Python 标准库，不安装 ROS、网页框架或 X11 组件。

## 2. 构建镜像

```bash
./scripts/build_image.sh
./scripts/build_camera_image.sh
```

第一条命令准备较小的官方样例包，构建 `gemini-isaac-ros:4.6-jazzy`。第二条准备 Orbbec 源码，构建 `gemini-isaac-ros:4.6-jazzy-camera-v2.10.6`。两者复用 Docker 构建缓存，不向镜像仓库推送。

`config/dependencies.lock.json` 固定 NVIDIA 基础镜像摘要、Orbbec 提交、样例包和数据集校验值。驱动文件清单位于 `docker/orbbec-source-manifest.json`。APT 依赖在构建时从上游仓库解析，因此这些固定输入不代表逐字节可重复构建。

官方样例包经校验后仅提取启动与配置文件，不伪造为 APT 已安装状态。核心二进制在镜像内通过 APT 安装，不包含当前路径不使用的人物推理栈。

## 3. 准备可选数据

```bash
python3 scripts/prepare.py visual_slam
python3 scripts/prepare.py nvblox
```

数据来自 NVIDIA 官方 NGC 资源，需要网络及适用的上游使用条款。中断下载保留 `.part` 文件，完整数据必须匹配固定字节数和 SHA-256 才能解压。解压使用 Python 的 data filter，并检查可用空间。元数据标记可避免重复解压，但不等于对用户手动修改过的全部录包文件重新审计。

`python3 scripts/prepare.py all` 会准备全部依赖及两套数据。空间有限时建议分目标执行。重复使用驱动源码和样例配置时会校验内容；已修改的文件会保留并报错，不自动覆盖。

## 4. 本地存储

| 目录 | 内容 |
| --- | --- |
| `.cache/` | 下载输入、分段文件和准备标记。 |
| `docker/orbbec-src/` | 下载的驱动源码、原始声明和 x64 SDK 动态库。 |
| `docker/official-examples/` | 提取的官方样例配置。 |
| `assets/` | 解压的数据集。 |
| `runs/` | 报告、日志、相机录包和导出网格。 |

这些目录均排除在 Git 之外。确认解压有效后可删除下载归档以节省空间；保留准备标记才能复用已解压数据。不要在构建或录制过程中删除输入文件。

下一步：[相机操作](CAMERA-zh.md)或[维护检查](DEVELOPMENT-zh.md)。

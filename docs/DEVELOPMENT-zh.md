# 维护与检查

[English](DEVELOPMENT.md) · [简体中文](DEVELOPMENT-zh.md) · [首页](../README-zh.md)

## 1. 源码检查

```bash
python3 -B -m unittest discover -s tests -v
for f in scripts/*.sh docker/camera-entrypoint.sh; do bash -n "$f"; done
```

测试覆盖依赖完整性、中断恢复、已修改源码保留和归档路径边界，不依赖 ROS、Docker、GPU 或相机，也不能替代运行验证。


实时查看器检查还覆盖增量网格替换/删除、非法数据原子拒绝、ESDF 坐标和未知区域、只读 HTTP 与停止进程身份。图像编码测试需要容器中的 NumPy/OpenCV，宿主缺少时会明确跳过；在已有待命容器内执行 `./scripts/live.sh exec python3 -m unittest discover -s /workspaces/isaac_ros-dev/tests -p test_live_images.py -v`。

## 2. 容器检查

```bash
./scripts/validate_environment.sh gpu
./scripts/validate_camera_setup.sh
```

第二条检查驱动与容器策略，执行真实 CUDA 内核，并以 `start_camera=false` 启动 VSLAM/nvblox。它拒绝复用已有实机容器，不会打开相机。

回放前先通过 `scripts/prepare.py` 准备可选数据：

```bash
./scripts/validate_environment.sh vslam
./scripts/validate_environment.sh nvblox
# 或同时检查两套数据：
./scripts/validate_environment.sh all
```

每次运行把日志和报告保存在 `runs/`。复用其他磁盘数据时，把 `ISAAC_ASSETS_DIR` 设为包含 `isaac_ros_visual_slam/` 和 `isaac_ros_nvblox/` 的绝对目录，容器会只读映射它。需要核对镜像身份并检查实际输出、服务返回和 PLY 内容。样例回放有效不代表实时精度测量通过。

## 3. 架构维护

追踪变更入口后再编辑 `docs/architecture/architecture.json`，同步更新源码行、关系、场景、不确定项和快照身份。安装了 arch-flow 时，使用它的实际本地辅助脚本重新生成：

```bash
python3 -B /path/to/arch-flow/scripts/build_map.py \
  docs/architecture/architecture.json --repo . \
  --output docs/architecture --force
```

将 `/path/to/arch-flow` 替换为已安装 Skill 的路径。辅助脚本属于维护工具，不是应用运行依赖。打开重新生成的 HTML，检查缩放、平移、复位、展开、证据、场景边界与高亮。中英文静态总览需要与模型一致。

## 4. 修改与发布

下载的 SDK、数据、缓存、录包和报告不进入 Git。保留上游声明，修改使用方式或能力时同步更新两种语言。除语法外还要检查链接及 README 实际渲染，只发布已审查的源码快照。本项目没有自动发布版本或推送镜像的流程。

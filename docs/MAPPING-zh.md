# 建图模式与地图保存

[English](MAPPING.md) · [简体中文](MAPPING-zh.md)

## 1. 选择模式

这是原项目在 Ubuntu 24.04 / Isaac ROS 4.6 / x86_64 上的功能移植，不能据此声称重现了 Jetson / Humble / Isaac ROS 3.0 的平台性能或视频效果。完整房间、绕行重访与动态场景需要实际扫描验证。

| 模式 | 输入与输出 | 使用目的 |
| --- | --- | --- |
| `baseline`（默认） | 关闭投射器；30 FPS 双目 VO；无彩色融合的局部 TSDF/ESDF | 排查相机、定位和基础链路 |
| `original` | 60 FPS 同步 RGB/深度/IR；按元数据分流无激光 IR 和有激光深度；彩色动态 nvblox；局部 `odom` 地图 | 对应上游组合示例；全局 SLAM 关闭，局部地图清除半径 7 m |
| `persistent` | 同上分流；彩色静态 nvblox，不按距离清除或衰减；开启全局 SLAM；独立 CPU 全局表面地图 | 保留扫描区域，并按优化后的历史位姿重建旧表面 |
| `vio` 命令 | 30 FPS 无投射双目 + 同步 IMU，输出视觉惯性位姿 | 对应独立定位示例；不启动 nvblox |

`original` 和 `persistent` 使用派生相机镜像。补丁仅为 ROS 驱动暴露 SDK 的 `OB_PROP_LASER_ON_OFF_PATTERN_INT`（旧名称 `OB_PROP_LASER_ON_OFF_MODE_INT`），每次启动设置并读回，不调用固件升级或保存设置接口。基线模式显式恢复为 0。实际分流依赖每帧 `frame_emitter_mode`，缺失或非法元数据会丢弃该帧，绝不按帧序号猜测。当前配置以 335L 为参考；其他固件和 336L 仍需验证 profile 和元数据。

## 2. 启动和查看

```bash
./scripts/build_camera_image.sh
./scripts/live.sh start
GEMINI_PROFILE=original ./scripts/live.sh visualize
# 停止后切换到长期保留与全局纠图模式：
GEMINI_PROFILE=persistent ./scripts/live.sh visualize
# 独立 VIO；前一个采集必须先停止：
./scripts/live.sh vio
```

所有采集入口共用管线锁。用 Ctrl+C 或另一个终端的 `./scripts/live.sh visualize-stop` 停止查看器。查看器在 [本机页面](http://127.0.0.1:8770/) 提供：

- **局部 nvblox**：彩色三维表面、轨迹、RGB/深度与真实 ESDF 切片；`original` 显示静态和动态组合距离场。参考网格不是地面检测；彩虹距离场不是表面颜色。
- **全局纠图**：独立 `map` 坐标系的历史关键帧融合表面。为避免混用坐标，不叠加局部 `odom` ESDF/轨迹。显示关键帧数、重建状态、历史位姿变化次数及容量错误。
- **表面边界**：青色线表示观测表面的开边界，包括深度孔洞和扫描边缘。墙面与障碍物必须实际被相机看见；开边界不是自动识别的房间外轮廓、虚拟围栏或导航安全边界。没有观测到的空间保持未知。

静置只能验证出流、建图更新与接口。扫描时缓慢移动、保持视野重叠，绕行后从接近原来的视角重访纹理丰富的静态区域。大面积人员运动、白墙、玻璃或快速甩动会影响定位；反复看同一点不保证触发回环。

## 3. 历史地图如何纠正

`persistent` 查询 cuVSLAM `GetAllPoses` 提供的优化后历史位姿。深度帧按原始时间戳插值里程计，关联时间差不超过 50 ms 的 SLAM 锚点，再乘标定外参；禁止用最新 TF 代替历史位姿。每个关键帧保存自己的局部表面和锚点相对变换。

当已有锚点位姿变化超过 5 mm 或 0.2° 时，重新投影并融合全部保留的关键帧，完整新版本就绪后替换旧几何。计数表示历史位姿变化，**不等于已检测到的回环次数**。原始 nvblox 局部 TSDF 不会被这个模块重新积分；全局地图是独立的 CPU 表面融合，采用 8 像素深度采样和 4 cm 顶点体素融合，不是第二套 nvblox TSDF，也不提供全局 ESDF。

关键帧按约 10 cm / 8° / 2 秒选取，受有效位姿和图像到达影响。每次会话最多 600 帧、512 MiB 未压缩关键帧数据；磁盘少于 1 GiB 时暂停新增。全局网格最多 500,000 顶点、1,000,000 个三角面。位姿查询上限 60,000 条，达到上限需新建会话。达到容量时保留已有地图并明确报错，不悄悄删除旧区域。原始现场不是静态时，全局静态表面仍可能留下移动物体痕迹。

## 4. 保存、恢复与离线查看

正常停止会尝试导出局部 `reports/live-mesh.ply`。`persistent` 额外保存：

- `global/keyframe-*.npz`：局部表面、颜色、时间戳和锚点关系。
- `global/global-state.json`：原子写入的完整版本清单与优化位姿，断电后重建仅使用清单内关键帧。
- `global/global-mesh.json` 与 `global/global-mesh.ply`：全局三维表面。
- `global/slam-map/`：尝试调用 cuVSLAM 保存服务；以报告中的 `slam_map_saved` 为准。
- `reports/viewer-snapshot.json`：停止时的局部/全局地图及最后预览帧，用于浏览器离线查看。

```bash
# 不打开相机、不需要启动 ROS；将路径替换为实际会话目录
python3 scripts/live_view.py --replay runs/<会话目录>
# 根据已保存的关键帧与优化位姿重新融合，运行在待命容器内
./scripts/live.sh exec python3 /workspaces/isaac_ros-dev/scripts/rebuild_global.py \
  /workspaces/isaac_ros-dev/runs/<会话目录>/global
```

离线查看仍明确显示“采集已停止”，不是实时采集。保存的快照包含现场最后图像，应留在本地 `runs/`；该目录不进入 Git。离线重建不启动新的回环优化。自动加载旧 SLAM 地图并跨会话继续融合尚未实现。

## 5. 验证边界

软件测试覆盖精确时间分流、非法元数据拒绝、历史关键帧独立纠正、旧几何替换、深度孔洞、容量限制和保存恢复；它们不能替代真实绕行后的回环验收。参考设备上的静置检查也不能证明动态障碍清除、完整房间闭合、回环纠正幅度或测量精度。原项目的视频是目标观感，不是本项目已经达到的结果保证。

维护验证入口见 [开发指南](DEVELOPMENT-zh.md)。原项目与参考接口：[Orbbec 示例](https://github.com/orbbec/isaac_ros-dev)、[激光交替属性](https://orbbec.github.io/docs/OrbbecSDKv2/_property_8h.html)。

ARG BASE_IMAGE=nvcr.io/nvidia/isaac/ros@sha256:4e2c1db3fa880649bc0aeefcc3d2a263d9c636e4ce8a30803cd784bd26f43442
FROM ${BASE_IMAGE}
USER root
ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy
ENV ISAAC_ROS_WS=/workspaces/isaac_ros-dev
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN --mount=type=cache,id=isaac-orbbec-apt-4.6,target=/var/cache/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && printf '%s\n' 'Acquire::Retries "5";' 'Acquire::http::Timeout "30";' 'Acquire::https::Timeout "30";' > /etc/apt/apt.conf.d/80-isaac-download \
    && rm -f /var/lib/apt/lists/*isaac* \
    && apt-get update --error-on=any \
    && apt-get install -y --no-install-recommends \
      ros-jazzy-isaac-ros-visual-slam \
      ros-jazzy-nvblox-ros \
      ros-jazzy-nvblox-image-padding \
      ros-jazzy-isaac-ros-launch-utils \
      ros-jazzy-semantic-label-conversion \
      ros-jazzy-isaac-ros-examples \
      ros-jazzy-rosbag2-storage-mcap \
      ros-jazzy-rviz2 \
      python3-numpy \
    && rm -rf /var/lib/apt/lists/*
COPY official-examples/ /
WORKDIR /workspaces/isaac_ros-dev
ENTRYPOINT ["/bin/bash"]
CMD ["-lc", "source /opt/ros/jazzy/setup.bash && exec bash"]

LABEL io.gemini-workbench.base="isaac-ros-4.6-jazzy"

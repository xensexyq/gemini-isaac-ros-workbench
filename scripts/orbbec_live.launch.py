"""Gemini 335L/336L: camera diagnostics, stereo VO, or depth-only mapping.

No IMU fusion, emitter interleaving, firmware changes, GUI, or navigation.
"""
from pathlib import Path
import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode


def _launch(context):
    def arg(name):
        return LaunchConfiguration(name).perform(context)

    mode = arg('mode')
    use_sim_time = arg('use_sim_time').lower() == 'true'
    if mode not in ('camera', 'vslam', 'mapping'):
        raise ValueError('mode 必须是 camera、vslam 或 mapping')
    with open(arg('camera_config'), encoding='utf-8') as stream:
        camera = yaml.safe_load(stream)
    camera.update(camera_name='camera', serial_number=arg('serial_number'),
                  use_sim_time=use_sim_time,
                  enable_depth=mode in ('camera', 'mapping'),
                  enable_color=mode == 'camera' or arg('preview_images').lower() == 'true')
    actions = []
    if arg('start_camera').lower() == 'true':
        actions.append(ComposableNodeContainer(
            name='camera_container', namespace='camera',
            package='rclcpp_components', executable='component_container',
            composable_node_descriptions=[ComposableNode(
                package='orbbec_camera', plugin='orbbec_camera::OBCameraNodeDriver',
                name='camera', namespace='camera', parameters=[camera])],
            output='screen'))
    if mode in ('vslam', 'mapping'):
        slam = ComposableNode(
            name='visual_slam_node', package='isaac_ros_visual_slam',
            plugin='nvidia::isaac_ros::visual_slam::VisualSlamNode',
            parameters=[{
                'num_cameras': 2, 'tracking_mode': 0,
                'use_sim_time': use_sim_time,
                'rectified_images': False,
                'enable_image_denoising': False,
                'base_frame': 'camera_link',
                'map_frame': 'map', 'odom_frame': 'odom',
                'camera_optical_frames': ['camera_left_ir_optical_frame',
                                          'camera_right_ir_optical_frame'],
                'image_jitter_threshold_ms': 50.0,
                'enable_slam_visualization': True,
                'enable_landmarks_view': True,
                'enable_observations_view': True,
            }], remappings=[
                ('visual_slam/image_0', '/camera/left_ir/image_raw'),
                ('visual_slam/image_1', '/camera/right_ir/image_raw'),
                ('visual_slam/camera_info_0', '/camera/left_ir/camera_info'),
                ('visual_slam/camera_info_1', '/camera/right_ir/camera_info')])
        actions.append(ComposableNodeContainer(
            name='visual_slam_container', namespace='', package='rclcpp_components',
            executable='component_container_isolated', arguments=['--use_multi_threaded_executor'],
            composable_node_descriptions=[slam], output='screen'))
    if mode == 'mapping':
        base = Path(get_package_share_directory('nvblox_examples_bringup')) / 'config/nvblox/nvblox_base.yaml'
        mapping = ComposableNode(
            name='nvblox_node', package='nvblox_ros', plugin='nvblox::NvbloxNode',
            parameters=[str(base), {
                'num_cameras': 1, 'global_frame': 'odom',
                'use_sim_time': use_sim_time,
                'use_tf_transforms': True, 'use_depth': True,
                'use_color': False, 'use_lidar': False,
                'input_qos': 'SENSOR_DATA', 'voxel_size': 0.05,
                'map_clearing_frame_id': 'camera_link',
                'esdf_slice_bounds_visualization_attachment_frame_id': 'camera_link',
                'workspace_height_bounds_visualization_attachment_frame_id': 'camera_link',
            }], remappings=[
                ('camera_0/depth/image', '/camera/depth/image_raw'),
                ('camera_0/depth/camera_info', '/camera/depth/camera_info')])
        actions.append(ComposableNodeContainer(
            name='nvblox_container', namespace='', package='rclcpp_components',
            executable='component_container_isolated', arguments=['--use_multi_threaded_executor'],
            composable_node_descriptions=[mapping], output='screen'))
    actions.append(LogInfo(msg=f'模式={mode}；双目视觉定位；建图使用原生深度和 odom TF；实时输出请检查话题或查看器。'))
    return actions


def generate_launch_description():
    root = Path(__file__).resolve().parents[1]
    return LaunchDescription([
        DeclareLaunchArgument('mode', default_value='camera'),
        DeclareLaunchArgument('serial_number', default_value=''),
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('preview_images', default_value='false',
                              description='Enable RGB preview without color fusion'),
        DeclareLaunchArgument('camera_config', default_value=str(root / 'config/gemini330.yaml')),
        DeclareLaunchArgument('start_camera', default_value='true',
                              description='false 仅用于无相机检查或独立录包回放'),
        OpaqueFunction(function=_launch),
    ])

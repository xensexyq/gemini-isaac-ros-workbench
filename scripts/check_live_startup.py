#!/usr/bin/env python3
"""Start only VSLAM/nvblox, with the camera explicitly disabled."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import rclpy
from composition_interfaces.srv import ListNodes
from rcl_interfaces.srv import GetParameters
from rclpy.parameter import parameter_value_to_python

root = Path(__file__).resolve().parents[1]
report = Path(sys.argv[1])
log = Path(sys.argv[2])
result = {'camera_started': False, 'physical_camera_test': 'NOT RUN'}
with log.open('w') as output:
    process = subprocess.Popen([
        'ros2', 'launch', str(root / 'scripts/orbbec_live.launch.py'),
        'mode:=mapping', 'start_camera:=false'],
        stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    rclpy.init()
    node = rclpy.create_node('check_orbbec_live_startup')
    try:
        clients = [node.create_client(ListNodes, f'/{name}/_container/list_nodes')
                   for name in ('visual_slam_container', 'nvblox_container')]
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f'启动提前退出：{process.returncode}；参见 {log}')
            rclpy.spin_once(node, timeout_sec=0.2)
            services = dict(node.get_service_names_and_types())
            loaded = []
            for client in clients:
                if client.service_is_ready():
                    future = client.call_async(ListNodes.Request())
                    rclpy.spin_until_future_complete(node, future, timeout_sec=1.0)
                    if future.done() and future.result() is not None:
                        loaded.extend(future.result().full_node_names)
            if '/nvblox_node/save_ply' in services and \
               '/visual_slam_node' in loaded and '/nvblox_node' in loaded and \
               node.count_subscribers('/camera/left_ir/image_raw') > 0 and \
               node.count_subscribers('/camera/right_ir/image_raw') > 0 and \
               node.count_subscribers('/camera/depth/image_raw') > 0:
                break
        else:
            raise RuntimeError('节点接口在 120 秒内未就绪')
        names = node.get_node_names_and_namespaces()
        assert not any(name == 'camera' for name, namespace in names), names
        parameters = {}
        contracts = {
            'visual_slam_node': {'num_cameras': 2, 'tracking_mode': 0,
                                 'rectified_images': False, 'base_frame': 'camera_link',
                                 'map_frame': 'map', 'odom_frame': 'odom'},
            'nvblox_node': {'global_frame': 'odom', 'use_color': False,
                            'use_depth': True, 'input_qos': 'SENSOR_DATA'},
        }
        for target, expected in contracts.items():
            client = node.create_client(GetParameters, f'/{target}/get_parameters')
            assert client.wait_for_service(timeout_sec=5.0), target
            request = GetParameters.Request(names=list(expected))
            future = client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
            assert future.done() and future.result() is not None, target
            actual = dict(zip(expected, map(parameter_value_to_python, future.result().values)))
            assert actual == expected, (target, actual, expected)
            parameters[target] = actual
        result.update(status='PASS', nodes=names,
                      parameters=parameters,
                      subscriptions={topic: node.count_subscribers(topic) for topic in (
                          '/camera/left_ir/image_raw', '/camera/right_ir/image_raw',
                          '/camera/left_ir/camera_info', '/camera/right_ir/camera_info',
                          '/camera/depth/image_raw', '/camera/depth/camera_info')},
                      mesh_service=services['/nvblox_node/save_ply'])
        assert all(count > 0 for count in result['subscriptions'].values()), result
    except Exception as exc:
        result.update(status='FAIL', error=str(exc))
        raise
    finally:
        node.destroy_node()
        rclpy.shutdown()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        result['shutdown_exit_code'] = process.returncode
        report.write_text(json.dumps(result, indent=2, ensure_ascii=False))
text = log.read_text()
if process.returncode != 0 or any(marker in text for marker in ('process has died', 'terminate called', '[FATAL]')):
    result.update(status='FAIL', error='组件异常退出，参见启动日志')
    report.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    raise RuntimeError(result['error'])
print(json.dumps(result, indent=2, ensure_ascii=False))

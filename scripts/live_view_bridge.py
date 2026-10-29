#!/usr/bin/env python3
"""ROS worker, run inside the existing isolated camera container."""
import argparse
from collections import deque
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from live_mesh import MeshState
from live_layers import slice_snapshot, image_snapshot


def mapping_command(root, serial=''):
    command = ['ros2', 'launch', str(root / 'scripts/orbbec_live.launch.py'), 'mode:=mapping', 'preview_images:=true']
    if serial:
        command.append('serial_number:=' + serial)
    return command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial', default='')
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    run = Path(args.run)
    for child in ('logs', 'reports'):
        (run / child).mkdir(parents=True, exist_ok=True)
    (run / 'reports/bridge-pid.txt').write_text(str(os.getpid()))
    import rclpy
    from nav_msgs.msg import Odometry
    from nvblox_msgs.msg import Mesh, DistanceMapSlice
    from sensor_msgs.msg import Image
    from isaac_ros_visual_slam_interfaces.msg import VisualSlamStatus
    from rclpy.qos import QoSProfile, ReliabilityPolicy

    stop = False

    def request_stop(*_):
        nonlocal stop
        stop = True

    rclpy.init()
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    node = rclpy.create_node('gemini_live_view')
    mesh = MeshState()
    stats = dict(mesh_messages=0, odom_messages=0, rejected_mesh_updates=0,
                 mesh_revision=0, vo_state=0, max_displacement_m=0., error=None)
    last_mesh = last_odom = None
    pose = None
    path = deque(maxlen=6000)
    odom_times = deque()
    first_position = None
    layers = {}
    layer_times = {}
    image_attempts = {}
    layer_errors = {}

    def on_mesh(msg):
        nonlocal last_mesh
        try:
            blocks = []
            for block in msg.blocks:
                p = [v for point in block.vertices for v in (point.x, point.y, point.z)]
                n = [v for point in block.normals for v in (point.x, point.y, point.z)]
                blocks.append((p, n, list(block.triangles)))
            mesh.apply([(x.x, x.y, x.z) for x in msg.block_indices], blocks,
                       clear=msg.clear, frame=msg.header.frame_id)
            last_mesh = time.monotonic()
            stats['mesh_messages'] += 1
            stats['mesh_revision'] = mesh.revision
        except ValueError as error:
            stats['rejected_mesh_updates'] += 1
            stats['error'] = str(error)

    def on_odom(msg):
        nonlocal pose, last_odom, first_position
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        xyz, quat = [p.x, p.y, p.z], [q.x, q.y, q.z, q.w]
        if msg.header.frame_id != 'odom' or not all(map(math.isfinite, xyz + quat)):
            stats['error'] = 'Invalid odometry or frame; expected odom'
            return
        if not .9 < sum(x*x for x in quat) < 1.1:
            stats['error'] = 'Invalid odometry quaternion'
            return
        now = time.monotonic()
        last_odom = now
        odom_times.append(now)
        while odom_times and odom_times[0] < now - 5:
            odom_times.popleft()
        first_position = first_position or xyz
        stats['max_displacement_m'] = max(stats['max_displacement_m'], math.dist(first_position, xyz))
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9
        pose = dict(position=xyz, quaternion=quat, stamp=stamp)
        if not path or math.dist(path[-1], xyz) > .003:
            path.append(xyz)
        stats['odom_messages'] += 1

    def on_status(msg):
        stats['vo_state'] = int(msg.vo_state)

    def on_slice(msg):
        now = time.monotonic()
        if now - layer_times.get('esdf', -1e9) < .45:
            return
        try:
            layers['esdf'] = slice_snapshot(msg)
            layer_times['esdf'] = now
            layer_errors.pop('esdf', None)
        except ValueError as error:
            layer_errors['esdf'] = str(error)

    def on_image(msg, kind):
        now = time.monotonic()
        if now - image_attempts.get(kind, -1e9) < .45:
            return
        image_attempts[kind] = now
        try:
            layers[kind] = image_snapshot(msg, kind)
            layer_times[kind] = now
            layer_errors.pop(kind, None)
        except (ValueError, RuntimeError) as error:
            layer_errors[kind] = str(error)

    subscriptions = [
        node.create_subscription(Mesh, '/nvblox_node/mesh', on_mesh,
                                 QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE)),
        node.create_subscription(Odometry, '/visual_slam/tracking/odometry', on_odom,
                                 QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)),
        node.create_subscription(VisualSlamStatus, '/visual_slam/status', on_status, 10),
        node.create_subscription(DistanceMapSlice, '/nvblox_node/static_map_slice', on_slice, 1),
        node.create_subscription(Image, '/camera/color/image_raw', lambda m: on_image(m, 'color'),
                                 QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)),
        node.create_subscription(Image, '/camera/depth/image_raw', lambda m: on_image(m, 'depth'),
                                 QoSProfile(depth=1, reliability=ReliabilityPolicy.BEST_EFFORT)),
    ]
    root = Path(__file__).resolve().parents[1]
    log = (run / 'logs/mapping.log').open('w')
    launch = subprocess.Popen(mapping_command(root, args.serial),
                              cwd=run, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    emitted_revision = -1
    sequence = 0
    next_emit = time.monotonic()
    started = time.monotonic()

    def emit(running):
        nonlocal sequence, emitted_revision
        now = time.monotonic()
        hz = (len(odom_times)-1)/(odom_times[-1]-odom_times[0]) if len(odom_times) > 1 else 0.
        meta = dict(stats, sequence=sequence, running=running, frame='odom',
                    wall_time=time.time(), elapsed_seconds=now-started,
                    mesh_age_ms=(now-last_mesh)*1000 if last_mesh is not None else None,
                    odom_age_ms=(now-last_odom)*1000 if last_odom is not None else None,
                    odom_hz=hz, pose=pose, path=list(path),
                    pose_stamp_age_ms=(time.time()-pose['stamp'])*1000 if pose else None)
        meta['layer_errors'] = dict(layer_errors)
        meta['layer_age_ms'] = {k: (now-v)*1000 for k, v in layer_times.items()}
        meta['esdf_cells'] = layers.get('esdf', {}).get('count', 0)
        packet = dict(meta=meta, layers=dict(layers, sequence=sequence))
        if mesh.revision != emitted_revision:
            packet['mesh'] = mesh.snapshot()
            emitted_revision = mesh.revision
            stats['vertices'] = packet['mesh']['vertices']
            stats['triangles'] = packet['mesh']['triangles']
            stats['blocks'] = packet['mesh']['blocks']
            meta.update(vertices=stats['vertices'], triangles=stats['triangles'], blocks=stats['blocks'])
        else:
            meta.update({k: stats.get(k, 0) for k in ('vertices', 'triangles', 'blocks')})
        sys.stdout.write(json.dumps(packet, separators=(',', ':'), allow_nan=False) + '\n')
        sys.stdout.flush()
        (run / 'reports/bridge-summary.json').write_text(json.dumps(meta, indent=2))
        sequence += 1

    try:
        while not stop:
            rclpy.spin_once(node, timeout_sec=.02)
            if launch.poll() is not None:
                lines = (run / 'logs/mapping.log').read_text(errors='replace').splitlines()
                detail = lines[-1][:300] if lines else '请查看当次 mapping.log'
                stats['error'] = f'建图启动失败（{launch.returncode}）：{detail}'
                break
            now = time.monotonic()
            if now >= next_emit:
                emit(True)
                next_emit = time.monotonic() + .5
    except BrokenPipeError:
        stop = True
    finally:
        # Export while the mapping node is still alive, then release the camera.
        if stats.get('vertices', 0) and launch.poll() is None and rclpy.ok():
            try:
                from nvblox_msgs.srv import FilePath
                client = node.create_client(FilePath, '/nvblox_node/save_ply')
                if not client.wait_for_service(timeout_sec=1):
                    raise RuntimeError('save_ply unavailable')
                request = FilePath.Request()
                request.file_path = str(run / 'reports/live-mesh.ply')
                future = client.call_async(request)
                rclpy.spin_until_future_complete(node, future, timeout_sec=6)
                success = bool(future.done() and future.result() and future.result().success)
                stats['ply_export_success'] = success
                if success:
                    stats['ply_bytes'] = Path(request.file_path).stat().st_size
                    stats['ply_path'] = request.file_path
                else:
                    stats['export_error'] = 'save_ply failed or timed out'
            except Exception as error:
                stats['ply_export_success'] = False
                stats['export_error'] = str(error)
        if launch.poll() is None:
            os.killpg(launch.pid, signal.SIGINT)
            try:
                launch.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(launch.pid, signal.SIGKILL)
                launch.wait(timeout=5)
        stats['launch_exit_code'] = launch.returncode
        try:
            emit(False)
        except BrokenPipeError:
            pass
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        log.close()
    return 0 if not stats['error'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

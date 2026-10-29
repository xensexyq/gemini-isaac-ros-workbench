#!/usr/bin/env python3
"""Record actual ROS outputs; require finite moving poses or nonempty mesh."""
import argparse
import json
import math
import pathlib
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from rosidl_runtime_py.utilities import get_message

parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=["vslam", "nvblox"])
parser.add_argument("output")
parser.add_argument("--seconds", type=float, default=100)
args = parser.parse_args()
rclpy.init()
node = Node("isaac_validation_observer")
records = {}
subscriptions = {}
started = time.monotonic()
qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE)

def receive(topic, kind, message):
    rec = records.setdefault(topic, {"type": kind, "messages": 0})
    rec["messages"] += 1
    if kind in ["nav_msgs/msg/Odometry", "geometry_msgs/msg/PoseStamped"]:
        pose = message.pose.pose if kind == "nav_msgs/msg/Odometry" else message.pose
        position = [pose.position.x, pose.position.y, pose.position.z]
        orientation = [pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w]
        if not all(math.isfinite(x) for x in position + orientation) or not 0.9 < sum(x*x for x in orientation) < 1.1:
            rec["invalid_pose"] = True
        rec.setdefault("first_position", position)
        rec["last_position"] = position
        rec["max_displacement_m"] = max(rec.get("max_displacement_m", 0), math.dist(rec["first_position"], position))
    if kind == "nvblox_msgs/msg/Mesh":
        rec["max_blocks"] = max(rec.get("max_blocks", 0), len(message.blocks))
        vertices = sum(len(block.vertices) for block in message.blocks)
        rec["max_vertices"] = max(rec.get("max_vertices", 0), vertices)
    if kind == "nvblox_msgs/msg/MeshSerialized":
        rec["max_vertices"] = max(rec.get("max_vertices", 0), message.num_vertices)
        rec["max_triangles"] = max(rec.get("max_triangles", 0), message.num_triangles)
    if kind == "nvblox_msgs/msg/DistanceMapSlice":
        rec["max_cells"] = max(rec.get("max_cells", 0), len(message.data))
        rec["finite_observed_cells"] = max(rec.get("finite_observed_cells", 0), sum(math.isfinite(float(x)) and float(x) != message.unknown_value for x in message.data))

def discover():
    relevant = {"nav_msgs/msg/Odometry", "geometry_msgs/msg/PoseStamped", "nvblox_msgs/msg/Mesh", "nvblox_msgs/msg/MeshSerialized", "nvblox_msgs/msg/DistanceMapSlice"}
    for topic, types in node.get_topic_names_and_types():
        kind = types[0] if len(types) == 1 else ""
        if kind not in relevant or topic in subscriptions:
            continue
        subscriptions[topic] = node.create_subscription(get_message(kind), topic, lambda msg, t=topic, k=kind: receive(t, k, msg), qos)
node.create_timer(1, discover)
try:
    while time.monotonic() - started < args.seconds:
        rclpy.spin_once(node, timeout_sec=0.2)
finally:
    node.destroy_node()
    rclpy.shutdown()
if args.mode == "vslam":
    passed = any("visual_slam" in topic and rec["messages"] >= 10 and rec.get("max_displacement_m", 0) > 0.01 and not rec.get("invalid_pose") for topic, rec in records.items())
else:
    passed = any(rec.get("max_vertices", 0) > 0 for rec in records.values())
report = {"mode": args.mode, "status": "PASS" if passed else "FAIL", "elapsed_seconds": round(time.monotonic()-started, 2), "topics": records}
pathlib.Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
raise SystemExit(0 if passed else 1)

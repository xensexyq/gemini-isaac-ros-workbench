#!/usr/bin/env python3
import argparse
import time
import rclpy
from rclpy.node import Node
p=argparse.ArgumentParser()
p.add_argument("topic")
p.add_argument("--timeout",type=float,default=60)
p.add_argument("--subscribers",action="store_true")
a=p.parse_args()
rclpy.init()
n=Node("isaac_ready_check")
start=time.monotonic()
ready=False
try:
    while time.monotonic()-start<a.timeout:
        rclpy.spin_once(n,timeout_sec=0.2)
        if a.subscribers:
            ready=bool(n.get_subscriptions_info_by_topic(a.topic))
        else:
            ready=any(t==a.topic for t,_ in n.get_topic_names_and_types())
        if ready:break
finally:
    n.destroy_node()
    rclpy.shutdown()
print("READY" if ready else "TIMEOUT",a.topic,flush=True)
raise SystemExit(0 if ready else 1)

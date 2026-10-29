#!/usr/bin/env python3
"""Metadata-exact Laser On-Off routing; unknown emitter states fail closed.

Functional adaptation of the upstream routing contract; no image sequence parity
assumptions. Bounded pending queues tolerate metadata/image delivery reordering.
"""
from collections import OrderedDict, Counter
import json


class ExactEmitterGate:
    def __init__(self, emitter, capacity=12):
        self.emitter, self.capacity = emitter, capacity
        self.images, self.metadata = OrderedDict(), OrderedDict()
        self.counts = Counter()

    def add(self, stamp, value, metadata=False):
        queue = self.metadata if metadata else self.images
        queue[stamp] = value
        while len(queue) > self.capacity:
            queue.popitem(last=False)
            self.counts['expired_metadata' if metadata else 'expired_image'] += 1
        if stamp not in self.images or stamp not in self.metadata:
            return None
        image, raw = self.images.pop(stamp), self.metadata.pop(stamp)
        try:
            mode = json.loads(raw)['frame_emitter_mode']
            if type(mode) is not int or mode not in (0, 1):
                raise ValueError('Unknown emitter state')
        except (ValueError, KeyError, TypeError):
            self.counts['invalid_metadata'] += 1
            return None
        self.counts['on' if mode else 'off'] += 1
        if mode != self.emitter:
            return None
        self.counts['published'] += 1
        return image


def main():
    import rclpy
    from sensor_msgs.msg import Image
    from orbbec_camera_msgs.msg import Metadata
    from std_msgs.msg import String
    from rclpy.qos import QoSProfile, ReliabilityPolicy
    rclpy.init()
    node = rclpy.create_node('emitter_splitter')
    qos = QoSProfile(depth=12, reliability=ReliabilityPolicy.BEST_EFFORT)
    gates, handles = {}, []
    for stream in ('left_ir', 'right_ir', 'depth'):
        gate = gates[stream] = ExactEmitterGate(int(stream == 'depth'))
        pub = node.create_publisher(Image, '/splitter/' + stream, qos)
        def callback(msg, metadata=False, gate=gate, pub=pub):
            stamp = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
            output = gate.add(stamp, msg.json_data if metadata else msg, metadata)
            if output is not None:
                pub.publish(output)
        handles.append(node.create_subscription(Image, '/camera/' + stream + '/image_raw', callback, qos))
        handles.append(node.create_subscription(Metadata, '/camera/' + stream + '/metadata',
                       lambda m, cb=callback: cb(m, True), qos))
    status = node.create_publisher(String, '/splitter/status', 1)
    def report():
        status.publish(String(data=json.dumps({k: dict(v.counts) for k, v in gates.items()})))
    timer = node.create_timer(1., report)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok(): rclpy.shutdown()


if __name__ == '__main__':
    main()

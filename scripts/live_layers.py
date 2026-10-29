"""Bounded, truthful display products; no reconstruction or invented free space."""
from array import array
import base64
import math
import sys


def stamp_seconds(msg):
    return msg.header.stamp.sec + msg.header.stamp.nanosec / 1e9


def slice_snapshot(msg, max_cells=100000):
    w, h, res = int(msg.width), int(msg.height), float(msg.resolution)
    origin = [msg.origin.x, msg.origin.y, msg.origin.z]
    if msg.header.frame_id != 'odom':
        raise ValueError('ESDF frame must be odom')
    if w < 0 or h < 0 or w*h != len(msg.data) or w*h > 4000000:
        raise ValueError('Invalid ESDF dimensions or source budget exceeded')
    if res <= 0 or not all(map(math.isfinite, [res] + origin)):
        raise ValueError('Invalid ESDF resolution/origin')
    if max_cells < 1:
        raise ValueError('ESDF display budget must be positive')
    stride = max(1, math.ceil(math.sqrt(w*h/max_cells)))
    while math.ceil(w/stride)*math.ceil(h/stride) > max_cells:
        stride += 1
    values = array('f')
    for y in range(0, h, stride):
        for x in range(0, w, stride):
            distance = float(msg.data[y*w+x])
            if not math.isfinite(distance) or distance == msg.unknown_value:
                continue
            # ROS slice origin is a corner; display each observed cell at its center.
            values.extend((origin[0]+(x+.5)*res, origin[1]+(y+.5)*res, origin[2], distance))
    if sys.byteorder != 'little':
        values.byteswap()
    return dict(frame='odom', stamp=stamp_seconds(msg), resolution=res, stride=stride,
                origin=origin, width=w, height=h, count=len(values)//4,
                xyzd=base64.b64encode(values.tobytes()).decode())


def image_snapshot(msg, kind):
    import cv2
    import numpy as np
    if kind not in ('color', 'depth'):
        raise ValueError('Unknown preview kind')
    w, h, step = int(msg.width), int(msg.height), int(msg.step)
    if not 0 < w*h <= 16000000 or step*h != len(msg.data):
        raise ValueError('Invalid image dimensions/stride')
    if kind == 'color':
        if msg.encoding not in ('rgb8', 'bgr8') or step < w*3:
            raise ValueError('Unsupported color encoding: ' + msg.encoding)
        pixels = np.ndarray((h, w, 3), dtype=np.uint8, buffer=bytes(msg.data), strides=(step, 3, 1))
        if msg.encoding == 'rgb8':
            pixels = cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
        scale = None
    else:
        formats = {'16UC1': ('u2', .001), 'mono16': ('u2', .001), '32FC1': ('f4', 1.)}
        if msg.encoding not in formats:
            raise ValueError('Unsupported depth encoding: ' + msg.encoding)
        dtype, factor = formats[msg.encoding]
        dtype = np.dtype(('>' if msg.is_bigendian else '<') + dtype)
        if step < w*dtype.itemsize:
            raise ValueError('Depth stride too small')
        depth = np.ndarray((h, w), dtype=dtype, buffer=bytes(msg.data), strides=(step, dtype.itemsize)).astype(np.float32)*factor
        valid = np.isfinite(depth) & (depth > 0)
        pixels = np.zeros((h, w), dtype=np.uint8)
        # Fixed scale: white is near, dark is far; invalid samples remain black.
        pixels[valid] = (255 - np.clip((depth[valid]-.2)/4.8, 0, 1)*239).astype(np.uint8)
        scale = [.2, 5.0]
    if w > 640:
        pixels = cv2.resize(pixels, (640, max(1, round(h*640/w))), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode('.jpg', pixels, [cv2.IMWRITE_JPEG_QUALITY, 78])
    if not ok:
        raise RuntimeError('JPEG preview encoding failed')
    return dict(stamp=stamp_seconds(msg), frame=msg.header.frame_id, width=int(pixels.shape[1]),
                height=int(pixels.shape[0]), source_width=w, source_height=h,
                depth_range_m=scale, jpeg=base64.b64encode(encoded).decode())

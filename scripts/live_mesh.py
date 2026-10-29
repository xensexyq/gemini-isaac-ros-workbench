"""Validate and accumulate nvblox incremental meshes without ROS dependencies."""
from array import array
import base64
import math
import sys


class MeshState:
    def __init__(self, frame='odom', max_vertices=500_000):
        self.frame = frame
        self.max_vertices = max_vertices
        self.blocks = {}
        self.revision = 0

    def apply(self, indices, blocks, *, clear=False, frame='odom'):
        if frame != self.frame:
            raise ValueError(f'Mesh frame {frame!r} does not match {self.frame!r}')
        if len(indices) != len(blocks):
            raise ValueError('Mesh block indices and data lengths differ')
        updates = {}
        for key, block in zip(indices, blocks):
            if len(key) != 3 or not all(isinstance(x, int) for x in key):
                raise ValueError('Invalid block index')
            positions, normals, triangles = block
            if len(positions) % 3 or len(triangles) % 3:
                raise ValueError('Incomplete vertex or triangle')
            count = len(positions) // 3
            if len(normals) not in (0, len(positions)):
                raise ValueError('Normals do not match vertices')
            if not all(math.isfinite(x) and abs(x) < 100_000 for x in positions + normals):
                raise ValueError('Non-finite or excessive mesh coordinate')
            if not all(isinstance(x, int) and 0 <= x < count for x in triangles):
                raise ValueError('Triangle references an absent vertex')
            updates[tuple(key)] = (tuple(positions), tuple(normals or [0., 0., 1.] * count),
                                   tuple(triangles)) if count else None
        merged = {} if clear else self.blocks.copy()
        for key, value in updates.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        if sum(len(v[0]) // 3 for v in merged.values()) > self.max_vertices:
            raise ValueError('Map exceeds viewer vertex budget; last valid map retained')
        if clear or merged != self.blocks:
            self.blocks = merged
            self.revision += 1

    def snapshot(self):
        positions, normals, triangles = array('f'), array('f'), array('I')
        for p, n, t in self.blocks.values():
            offset = len(positions) // 3
            positions.extend(p)
            normals.extend(n)
            triangles.extend(x + offset for x in t)
        count = len(positions) // 3
        low = [min(positions[i::3]) for i in range(3)] if count else [0., 0., 0.]
        high = [max(positions[i::3]) for i in range(3)] if count else [0., 0., 0.]
        if sys.byteorder != 'little':
            for values in (positions, normals, triangles):
                values.byteswap()
        return dict(revision=self.revision, frame=self.frame, blocks=len(self.blocks),
                    vertices=count, triangles=len(triangles) // 3, low=low, high=high,
                    positions=base64.b64encode(positions.tobytes()).decode('ascii'),
                    normals=base64.b64encode(normals.tobytes()).decode('ascii'),
                    indices=base64.b64encode(triangles.tobytes()).decode('ascii'))

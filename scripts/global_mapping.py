"""Bounded, replayable global surface fusion from optimized historical poses.

This CPU surface map is separate from the local GPU nvblox TSDF/ESDF. Each
keyframe retains sensor geometry and its own SLAM anchor; optimization rebuilds
all geometry instead of applying a single rigid correction to an old mesh.
"""
import base64
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import os
import time

import numpy as np


def stamp_ns(header):
    return header.stamp.sec * 10**9 + header.stamp.nanosec


def matrix(position, quaternion):
    p, q = np.asarray(position, float), np.asarray(quaternion, float)
    if p.shape != (3,) or q.shape != (4,) or not np.isfinite(np.r_[p, q]).all():
        raise ValueError('Invalid pose')
    if not .9 < q @ q < 1.1:
        raise ValueError('Invalid quaternion')
    x, y, z, w = q / np.linalg.norm(q)
    result = np.eye(4)
    result[:3, :3] = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                       [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                       [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
    result[:3, 3] = p
    return result


def pose_matrix(pose):
    p, q = pose.position, pose.orientation
    return matrix([p.x, p.y, p.z], [q.x, q.y, q.z, q.w])


def interpolate(poses, stamp, max_gap_ns=100_000_000):
    """Never extrapolate a delayed image pose or silently use latest TF."""
    import cv2
    keys = sorted(poses)
    i = int(np.searchsorted(keys, stamp))
    if i < len(keys) and keys[i] == stamp:
        return poses[stamp]
    if i == 0 or i == len(keys) or keys[i]-keys[i-1] > max_gap_ns:
        return None
    a, b = poses[keys[i-1]], poses[keys[i]]
    alpha = (stamp-keys[i-1])/(keys[i]-keys[i-1])
    rv, _ = cv2.Rodrigues(a[:3, :3].T @ b[:3, :3])
    rot, _ = cv2.Rodrigues(rv*alpha)
    result = np.eye(4); result[:3, :3] = a[:3, :3] @ rot
    result[:3, 3] = a[:3, 3]*(1-alpha) + b[:3, 3]*alpha
    return result


def surface(depth, info, color, stride=8):
    """Calibrated depth mesh. Do not join holes/discontinuities with triangles."""
    import cv2
    if depth.encoding not in ('16UC1', 'mono16'):
        raise ValueError('Global map expects registered millimeter depth')
    w, h = depth.width, depth.height
    if (info.width, info.height) != (w, h) or depth.step < w*2:
        raise ValueError('Depth calibration/stride mismatch')
    dtype = '>u2' if depth.is_bigendian else '<u2'
    d = np.ndarray((h,w), dtype=dtype, buffer=depth.data, strides=(depth.step,2))
    yy, xx = np.mgrid[0:h:stride, 0:w:stride]
    z = d[::stride,::stride].astype(float).ravel()*.001
    uv = np.column_stack((xx.ravel(), yy.ravel())).astype(float)
    k = np.asarray(info.k).reshape(3,3)
    if k[0,0] <= 0 or k[1,1] <= 0 or info.distortion_model not in ('', 'plumb_bob', 'rational_polynomial'):
        raise ValueError('Unsupported global depth calibration')
    xy = cv2.undistortPoints(uv[:,None,:], k, np.asarray(info.d) if len(info.d) else None)[:,0,:]
    xyz = np.column_stack((xy*z[:,None], z))
    rgb = np.full(xyz.shape, .7)
    if color is not None and (color.width,color.height)==(w,h) and color.encoding in ('rgb8','bgr8'):
        pixels = np.ndarray((h,w,3), dtype=np.uint8, buffer=color.data, strides=(color.step,3,1))
        rgb = pixels[::stride,::stride].reshape(-1,3).astype(float)/255
        if color.encoding=='bgr8': rgb=rgb[:,::-1]
    ids = np.arange(len(z)).reshape(xx.shape)
    a,b,c,e = ids[:-1,:-1].ravel(),ids[:-1,1:].ravel(),ids[1:,:-1].ravel(),ids[1:,1:].ravel()
    faces=np.vstack((np.column_stack((a,b,c)),np.column_stack((b,e,c))))
    depths=z[faces]
    valid=np.isfinite(depths).all(axis=1)&(depths.min(axis=1)>.2)&(depths.max(axis=1)<5.)
    valid &= np.ptp(depths,axis=1)<(.08+.02*depths.min(axis=1))
    faces=faces[valid]
    used, inverse=np.unique(faces,return_inverse=True)
    return xyz[used].astype('f4'),rgb[used].astype('f4'),inverse.reshape(-1,3).astype('u4')


def fuse(frames, optimized, voxel=.04, max_vertices=500_000):
    """Re-fuse every retained keyframe using its independently updated anchor."""
    points,colors,faces=[],[],[]; offset=0
    for f in frames:
        transform=optimized[f['anchor']] @ f['relative']
        p=f['points'] @ transform[:3,:3].T+transform[:3,3]
        points.append(p);colors.append(f['colors']);faces.append(f['faces']+offset);offset+=len(p)
    if not points: return np.empty((0,3)),np.empty((0,3)),np.empty((0,3),dtype='u4')
    p,c,t=np.concatenate(points),np.concatenate(colors),np.concatenate(faces)
    keys=np.floor(p/voxel).astype(np.int64)
    _, inv=np.unique(keys,axis=0,return_inverse=True)
    count=np.bincount(inv)
    if len(count)>max_vertices:
        raise ValueError('Global vertex budget reached; previous complete map retained')
    out=np.zeros((len(count),3));col=out.copy()
    np.add.at(out,inv,p);np.add.at(col,inv,c)
    out/=count[:,None];col/=count[:,None]
    t=inv[t]
    t=t[(t[:,0]!=t[:,1])&(t[:,1]!=t[:,2])&(t[:,2]!=t[:,0])]
    if len(t):
        _,first=np.unique(np.sort(t,axis=1),axis=0,return_index=True);t=t[first]
    if len(t)>1_000_000:
        raise ValueError('Global triangle budget reached; previous complete map retained')
    return out.astype('f4'),col.astype('f4'),t.astype('u4')


def snapshot(points, colors, faces, revision):
    normals=np.zeros_like(points)
    if len(faces):
        tri=points[faces];n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        for i in range(3): np.add.at(normals,faces[:,i],n)
        normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-9)
    def pack(a,dtype): return base64.b64encode(np.asarray(a,dtype=dtype).tobytes()).decode()
    edges=np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]])) if len(faces) else np.empty((0,2),int)
    edges,counts=np.unique(np.sort(edges,axis=1),axis=0,return_counts=True)
    boundary=points[edges[counts==1]].reshape(-1,3)
    return dict(frame='map', revision=revision, vertices=len(points), triangles=len(faces),
                low=points.min(axis=0).tolist() if len(points) else [0,0,0],
                high=points.max(axis=0).tolist() if len(points) else [0,0,0],
                positions=pack(points,'<f4'),normals=pack(normals,'<f4'),colors=pack(colors,'<f4'),
                indices=pack(faces,'<u4'),boundary=pack(boundary,'<f4'),boundary_vertices=len(boundary))


def atomic_json(path, data):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,separators=(',',':'),allow_nan=False));os.replace(tmp,path)


class GlobalMap:
    def __init__(self, directory, max_frames=600, max_bytes=512*1024**2):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.max_frames,self.max_bytes=max_frames,max_bytes
        self.frames=[];self.optimized={};self.bytes=0;self.revision=0;self.corrections=0
        self.dirty=False;self.mesh=None;self.last_capture=None;self.input_version=0
        self.status=dict(state='waiting_for_optimized_poses', keyframes=0, corrections=0, error=None)

    def update_poses(self, poses):
        updated=False
        for stamp, pose in poses.items():
            if not np.isfinite(pose).all() or pose.shape != (4,4): raise ValueError('Invalid optimized pose')
            old=self.optimized.get(stamp)
            if old is not None and any(f['anchor']==stamp for f in self.frames):
                delta=np.linalg.inv(old) @ pose
                angle=math.acos(float(np.clip((np.trace(delta[:3,:3])-1)/2,-1,1)))
                if np.linalg.norm(delta[:3,3])>.005 or angle>math.radians(.2): updated=True
            self.optimized[stamp]=pose.copy()
        # Keep saved anchors plus recent service poses, never unbounded history.
        anchors={f['anchor'] for f in self.frames}
        keep=anchors|set(sorted(self.optimized)[-2400:])
        self.optimized={k:v for k,v in self.optimized.items() if k in keep}
        if updated:
            self.corrections+=1;self.dirty=True;self.input_version+=1
        self.status['corrections']=self.corrections

    def add(self, stamp, points, colors, faces, odom, extrinsic):
        if not len(points) or not self.optimized: return False
        pose=interpolate(odom,stamp)
        if pose is None: return False
        anchor=min(self.optimized,key=lambda s:abs(s-stamp))
        # Associating distant poses across relocalization would deform the map.
        if abs(anchor-stamp)>50_000_000: return False
        anchor_odom=interpolate(odom,anchor)
        if anchor_odom is None: return False
        if self.last_capture is not None:
            last_stamp,last_pose=self.last_capture
            delta=np.linalg.inv(last_pose)@pose
            angle=math.acos(float(np.clip((np.trace(delta[:3,:3])-1)/2,-1,1)))
            if stamp-last_stamp<2*10**9 and np.linalg.norm(delta[:3,3])<.10 and angle<math.radians(8): return False
        size=sum(x.nbytes for x in (points,colors,faces))
        import shutil
        if len(self.frames)>=self.max_frames or self.bytes+size>self.max_bytes or shutil.disk_usage(self.directory).free<1024**3:
            self.status.update(state='capacity_reached',error='Keyframe capacity reached; map retained, acquisition paused')
            return False
        relative=np.linalg.inv(anchor_odom)@pose@extrinsic
        frame=dict(stamp=stamp,anchor=anchor,relative=relative,points=points,colors=colors,faces=faces)
        target=self.directory/f'keyframe-{len(self.frames):04d}.npz'
        with target.with_suffix('.tmp').open('wb') as stream:
            np.savez_compressed(stream,**frame)
        os.replace(target.with_suffix('.tmp'),target)
        self.frames.append(frame);self.bytes+=size;self.last_capture=(stamp,pose);self.dirty=True;self.input_version+=1
        self.status.update(keyframes=len(self.frames),cache_bytes=self.bytes)
        return True

    def rebuild(self):
        if not self.dirty: return
        self.status['state']='rebuilding'
        points,colors,faces=fuse(self.frames,self.optimized)
        candidate=snapshot(points,colors,faces,self.revision+1)
        # Persist before replacing the displayed complete revision.
        self.persist_state(self.optimized, len(self.frames), self.revision+1)
        atomic_json(self.directory/'optimized-poses.json',{str(k):v.tolist() for k,v in self.optimized.items()})
        atomic_json(self.directory/'global-mesh.json',candidate)
        self.mesh=candidate;self.revision+=1;self.dirty=False
        self.status.update(state='ready',revision=self.revision,vertices=len(points),triangles=len(faces))

    def persist_state(self, poses, frame_count, revision):
        atomic_json(self.directory/'global-state.json',dict(schema=1,revision=revision,
            keyframes=[f'keyframe-{i:04d}.npz' for i in range(frame_count)],
            optimized_poses={str(k):v.tolist() for k,v in poses.items()}))

    def export(self):
        if self.dirty: self.rebuild()
        if self.mesh is None: return
        p=np.frombuffer(base64.b64decode(self.mesh['positions']),dtype='<f4').reshape(-1,3)
        c=np.frombuffer(base64.b64decode(self.mesh['colors']),dtype='<f4').reshape(-1,3)
        t=np.frombuffer(base64.b64decode(self.mesh['indices']),dtype='<u4').reshape(-1,3)
        target=self.directory/'global-mesh.ply'
        with target.with_suffix('.tmp').open('w') as stream:
            stream.write(f'ply\nformat ascii 1.0\nelement vertex {len(p)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nelement face {len(t)}\nproperty list uchar int vertex_indices\nend_header\n')
            for point,color in zip(p,c): stream.write(' '.join(map(str,point))+' '+' '.join(map(str,np.clip(color*255,0,255).astype(int)))+'\n')
            for triangle in t: stream.write('3 '+' '.join(map(str,triangle))+'\n')
        os.replace(target.with_suffix('.tmp'),target)


class GlobalCollector:
    """ROS adapter; all pose/image stamps retain their original sensor times."""
    def __init__(self, node, directory, depth_topic='/camera/depth/image_raw'):
        from sensor_msgs.msg import Image, CameraInfo
        from nav_msgs.msg import Odometry
        from isaac_ros_visual_slam_interfaces.msg import VisualSlamStatus
        from isaac_ros_visual_slam_interfaces.srv import GetAllPoses
        from rclpy.qos import QoSProfile,ReliabilityPolicy
        from tf2_ros import Buffer, TransformListener
        self.node=node;self.map=GlobalMap(directory);self.odom={};self.depth=deque(maxlen=30);self.colors=deque(maxlen=120)
        self.tracking=False
        self.info=None;self.pending=None;self.last_attempt=0.;self.last_build=0.;self.last_query=0.;self.extrinsics={}
        self.buffer=Buffer();self.listener=TransformListener(self.buffer,node)
        self.executor=ThreadPoolExecutor(max_workers=1);self.build=None;self.build_version=-1
        self.client=node.create_client(GetAllPoses,'/visual_slam/get_all_poses');self.srv=GetAllPoses
        qos=QoSProfile(depth=8,reliability=ReliabilityPolicy.BEST_EFFORT)
        def odom(msg):
            if msg.header.frame_id!='odom' or msg.child_frame_id!='camera_link': return
            self.odom[stamp_ns(msg.header)]=pose_matrix(msg.pose.pose)
            if len(self.odom)>1000: self.odom.pop(min(self.odom))
        def info(msg): self.info=msg
        def tracking(msg):
            self.tracking=msg.vo_state==1
            if not self.tracking: self.depth.clear()
        self.subs=[node.create_subscription(VisualSlamStatus,'/visual_slam/status',tracking,10),
                   node.create_subscription(Odometry,'/visual_slam/tracking/odometry',odom,qos),
                   node.create_subscription(Image,depth_topic,lambda msg: self.depth.append(msg),qos),
                   node.create_subscription(Image,'/camera/color/image_raw',lambda msg: self.colors.append(msg),qos),
                   node.create_subscription(CameraInfo,'/camera/depth/camera_info',info,qos)]

    def tick(self):
        from rclpy.time import Time
        now=time.monotonic()
        if self.pending is not None and self.pending.done():
            response=self.pending.result();self.pending=None
            if response and response.success:
                anchors={f['anchor'] for f in self.map.frames}
                selected=response.poses[-2400:]+[p for p in response.poses[:-2400] if stamp_ns(p.header) in anchors]
                poses={stamp_ns(p.header):pose_matrix(p.pose) for p in selected if p.header.frame_id in ('','map')}
                self.map.update_poses(poses);self.map.status['optimized_poses']=len(response.poses)
                self.map.status['pose_service']='ready'
                if len(response.poses)>=60000:
                    self.map.status['error']='Optimized trajectory query limit reached; start a new session'
            else: self.map.status['pose_service']='empty_or_failed'
        if self.pending is None and now-self.last_query>1 and self.client.service_is_ready():
            self.last_query=now;self.pending=self.client.call_async(self.srv.Request(max_count=60000))
        if self.tracking and now-self.last_attempt>.25 and self.depth and self.info is not None and self.map.status.get('optimized_poses',0)<60000:
            self.last_attempt=now
            # A modest delay allows historical SLAM poses to reach the service.
            depth=self.depth[0];stamp=stamp_ns(depth.header)
            color=min(self.colors,key=lambda m:abs(stamp_ns(m.header)-stamp)) if self.colors else None
            if color is not None and abs(stamp_ns(color.header)-stamp)>40_000_000: color=None
            frame=depth.header.frame_id
            if frame not in self.extrinsics:
                try:
                    tf=self.buffer.lookup_transform('camera_link',frame,Time()).transform
                    p,q=tf.translation,tf.rotation
                    self.extrinsics[frame]=matrix([p.x,p.y,p.z],[q.x,q.y,q.z,q.w])
                except Exception:
                    return
            p,c,t=surface(depth,self.info,color)
            self.map.add(stamp,p,c,t,self.odom,self.extrinsics[frame])
        if self.build is not None and self.build.done():
            points,colors,faces=self.build.result();self.build=None
            candidate=snapshot(points,colors,faces,self.map.revision+1)
            self.map.persist_state(self.build_poses,self.build_frame_count,self.map.revision+1)
            atomic_json(self.map.directory/'optimized-poses.json',{str(k):v.tolist() for k,v in self.build_poses.items()})
            atomic_json(self.map.directory/'global-mesh.json',candidate)
            self.map.mesh=candidate;self.map.revision+=1
            self.map.dirty=self.build_version!=self.map.input_version
            self.map.status.update(state='ready',revision=self.map.revision,vertices=len(points),triangles=len(faces))
        if self.build is None and now-self.last_build>3 and self.map.dirty:
            self.last_build=now;self.build_version=self.map.input_version
            self.build_poses={k:v.copy() for k,v in self.map.optimized.items()}
            self.build_frame_count=len(self.map.frames)
            self.map.status['state']='rebuilding'
            self.build=self.executor.submit(fuse,list(self.map.frames),self.build_poses)

    def close(self):
        self.executor.shutdown(wait=True)
        self.map.export()

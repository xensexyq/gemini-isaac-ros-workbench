import json
from pathlib import Path
import tempfile
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from emitter_splitter import ExactEmitterGate
from live_mesh import MeshState


class EmitterTests(unittest.TestCase):
    def test_exact_stamp_reordering_and_fail_closed(self):
        g=ExactEmitterGate(0)
        self.assertIsNone(g.add(1,'off-image'))
        self.assertIsNone(g.add(2,json.dumps({'frame_emitter_mode':0}),True))
        self.assertEqual(g.add(1,json.dumps({'frame_emitter_mode':0}),True),'off-image')
        self.assertIsNone(g.add(3,'wrong-state'))
        self.assertIsNone(g.add(3,json.dumps({'frame_emitter_mode':1}),True))
        self.assertIsNone(g.add(4,'bad'))
        self.assertIsNone(g.add(4,'{}',True))
        self.assertEqual(g.counts['published'],1)
        self.assertEqual(g.counts['invalid_metadata'],1)

    def test_queues_bounded_and_no_guessing_missing_metadata(self):
        g=ExactEmitterGate(1,capacity=2)
        for i in range(10): self.assertIsNone(g.add(i,'image'))
        self.assertEqual(len(g.images),2)
        self.assertEqual(g.counts['expired_image'],8)

    def test_mesh_rejects_bad_colors_atomically(self):
        m=MeshState();tri=([0.,0.,0.,1.,0.,0.,0.,1.,0.],[],[0,1,2])
        m.apply([(0,0,0)],[tri+([1.,0.,0.]*3,)])
        old=m.snapshot()
        with self.assertRaises(ValueError):m.apply([(0,0,0)],[tri+([2.]*9,)],clear=True)
        self.assertEqual(m.snapshot(),old)

try:
    import numpy as np
    import cv2
    from global_mapping import GlobalMap, matrix, interpolate, fuse, snapshot, surface
    HAS_ARRAYS=True
except ImportError:
    HAS_ARRAYS=False


@unittest.skipUnless(HAS_ARRAYS,'Run in camera container with numpy and OpenCV')
class GlobalMapTests(unittest.TestCase):
    def test_historical_nonrigid_pose_correction_replaces_old_geometry(self):
        p=np.array([[0,0,1],[.2,0,1],[0,.2,1]],dtype='f4');t=np.array([[0,1,2]],dtype='u4')
        a,b=np.eye(4),np.eye(4);b[0,3]=2
        frames=[dict(anchor=1,relative=np.eye(4),points=p,colors=p*0+.5,faces=t),
                dict(anchor=2,relative=np.eye(4),points=p,colors=p*0+.5,faces=t)]
        before=fuse(frames,{1:a,2:b})
        a=a.copy();b=b.copy();a[0,3]=.4;b[0,3]=1.5
        after=fuse(frames,{1:a,2:b})
        self.assertAlmostEqual(float(before[0][:,0].max()),2.2,places=5)
        self.assertAlmostEqual(float(after[0][:,0].min()),.4,places=5)
        self.assertAlmostEqual(float(after[0][:,0].max()),1.7,places=5)
        self.assertEqual(len(after[0]),6) # no old geometry appended

    def test_time_interpolation_and_no_extrapolation(self):
        a=np.eye(4);b=np.eye(4);b[0,3]=1
        self.assertIsNone(interpolate({0:a,100:b},101))
        self.assertAlmostEqual(interpolate({0:a,100:b},50)[0,3],.5)
        self.assertIsNone(interpolate({0:a,200_000_000:b},100_000_000))

    def test_saved_keyframes_capacity_and_optimization_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            g=GlobalMap(tmp,max_frames=1);g.update_poses({100:np.eye(4)})
            p=np.array([[0,0,1],[.2,0,1],[0,.2,1]],dtype='f4');t=np.array([[0,1,2]],dtype='u4')
            self.assertTrue(g.add(100,p,p*0+.7,t,{100:np.eye(4)},np.eye(4)))
            g.rebuild();old=g.mesh
            # A new pose alone is not a loop correction.
            g.update_poses({101:np.eye(4)});self.assertEqual(g.corrections,0)
            changed=np.eye(4);changed[0,3]=.2;g.update_poses({100:changed});g.rebuild()
            self.assertEqual(g.corrections,1);self.assertNotEqual(g.mesh['positions'],old['positions'])
            g.update_poses({3_000_000_000:np.eye(4)})
            self.assertFalse(g.add(3_000_000_000,p,p*0+.7,t,{3_000_000_000:np.eye(4)},np.eye(4)))
            self.assertEqual(len(g.frames),1);self.assertTrue(g.status['error'])
            g.export();self.assertTrue((Path(tmp)/'global-mesh.ply').exists())
            self.assertEqual(len(list(Path(tmp).glob('keyframe-*.npz'))),1)

    def test_boundary_is_observed_surface_edge_and_holes_not_filled(self):
        p=np.array([[0,0,1],[1,0,1],[0,1,1]],dtype='f4');t=np.array([[0,1,2]],dtype='u4')
        data=snapshot(p,p*0+.5,t,1)
        self.assertEqual(data['boundary_vertices'],6)
        self.assertEqual(data['triangles'],1)
        from types import SimpleNamespace as NS
        d=np.zeros((24,24),dtype='<u2');d[0,0]=1000;d[0,8]=3000;d[8,0]=1000
        msg=NS(encoding='16UC1',width=24,height=24,step=48,is_bigendian=False,data=d.tobytes())
        info=NS(width=24,height=24,k=[20.,0,12,0,20.,12,0,0,1],d=[],distortion_model='plumb_bob')
        points,colors,faces=surface(msg,info,None)
        self.assertEqual(len(faces),0) # don't connect two-meter discontinuity



@unittest.skipUnless(HAS_ARRAYS,'Run in camera container with numpy and OpenCV')
class RecoveryTests(unittest.TestCase):
    def test_manifest_only_references_complete_geometry_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            g=GlobalMap(tmp);g.update_poses({100:np.eye(4)})
            p=np.array([[0,0,1],[.2,0,1],[0,.2,1]],dtype='f4');t=np.array([[0,1,2]],dtype='u4')
            g.add(100,p,p*0+.5,t,{100:np.eye(4)},np.eye(4));g.rebuild()
            state=json.loads((Path(tmp)/'global-state.json').read_text())
            # An incomplete next capture is deliberately absent from committed manifest.
            (Path(tmp)/'keyframe-0001.npz').write_bytes(b'incomplete')
            self.assertEqual(state['keyframes'],['keyframe-0000.npz'])
            with np.load(Path(tmp)/state['keyframes'][0],allow_pickle=False) as data:
                self.assertIn(str(int(data['anchor'])),state['optimized_poses'])
                self.assertEqual(data['points'].shape,(3,3))

if __name__=='__main__': unittest.main()

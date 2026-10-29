"""Behavior checks for incremental maps and the local read-only API."""
import base64
from array import array
import gzip
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from live_mesh import MeshState
from live_view import Latest, handler_for, ThreadingHTTPServer, process_matches
import tempfile
import os

TRI = ([0., 0., 0., 1., 0., 0., 0., 1., 0.], [], [0, 1, 2])


class MeshAccumulationTests(unittest.TestCase):
    def test_incremental_updates_retain_other_blocks_and_offset_faces(self):
        state = MeshState()
        state.apply([(0, 0, 0)], [TRI])
        state.apply([(1, 0, 0)], [TRI])
        snap = state.snapshot()
        faces = array('I'); faces.frombytes(base64.b64decode(snap['indices']))
        self.assertEqual(snap['vertices'], 6)
        self.assertEqual(list(faces), [0, 1, 2, 3, 4, 5])

    def test_replacement_deletion_and_clear_do_not_append_stale_geometry(self):
        state = MeshState()
        state.apply([(0, 0, 0), (1, 0, 0)], [TRI, TRI])
        state.apply([(0, 0, 0)], [TRI])
        self.assertEqual(state.snapshot()['vertices'], 6)
        state.apply([(0, 0, 0)], [([], [], [])])
        self.assertEqual(state.snapshot()['vertices'], 3)
        state.apply([], [], clear=True)
        self.assertEqual(state.snapshot()['vertices'], 0)

    def test_invalid_update_is_atomic_even_when_clear_is_set(self):
        state = MeshState()
        state.apply([(0, 0, 0)], [TRI])
        previous = state.snapshot()
        for bad in [([float('nan'), 0., 0.], [], []), (TRI[0], [], [0, 1, 3])]:
            with self.assertRaises(ValueError):
                state.apply([(1, 0, 0)], [bad], clear=True)
            self.assertEqual(state.snapshot(), previous)
        with self.assertRaises(ValueError):
            state.apply([], [], frame='map')
        self.assertEqual(state.snapshot(), previous)

    def test_budget_exhaustion_preserves_last_valid_map(self):
        state = MeshState(max_vertices=3)
        state.apply([(0, 0, 0)], [TRI])
        with self.assertRaises(ValueError):
            state.apply([(1, 0, 0)], [TRI])
        self.assertEqual(state.snapshot()['vertices'], 3)


class ProcessIdentityTests(unittest.TestCase):
    def test_reused_pid_or_different_project_cannot_be_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); proc = root / '123'; proc.mkdir()
            # /proc fields after comm: state through starttime (field 22).
            fields = ['S'] + ['0'] * 18 + ['456']
            (proc / 'stat').write_text('123 (python3) ' + ' '.join(fields))
            (proc / 'cmdline').write_bytes(b'python3\0/another/project/live_view.py\0')
            self.assertFalse(process_matches({'pid': 123, 'start_ticks': '456'}, root))
            script = str(Path(__file__).resolve().parents[1] / 'scripts/live_view.py').encode()
            (proc / 'cmdline').write_bytes(b'python3\0' + script + b'\0')
            self.assertFalse(process_matches({'pid': 123, 'start_ticks': '457'}, root))
            self.assertTrue(process_matches({'pid': 123, 'start_ticks': '456'}, root))


class LiveApiTests(unittest.TestCase):
    def setUp(self):
        self.latest = Latest()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.latest))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)

    def request(self, path, host=None):
        client = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        client.request('GET', path, headers={'Host': host or f'127.0.0.1:{self.server.server_port}'})
        response = client.getresponse()
        data = response.read(); status = response.status
        client.close()
        return status, data

    def test_latest_mesh_survives_metadata_only_updates_and_stopped_state(self):
        self.latest.update({'meta': {'sequence': 1, 'running': True}, 'mesh': {'revision': 7, 'vertices': 3}})
        self.latest.update({'meta': {'sequence': 2, 'running': False}})
        status, data = self.request('/api/state')
        meta = json.loads(data)
        self.assertEqual(status, 200)
        self.assertFalse(meta['running'])
        self.assertEqual(meta['available_mesh_revision'], 7)
        self.assertGreaterEqual(meta['relay_age_ms'], 0)
        _, data = self.request('/api/mesh')
        self.assertEqual(json.loads(gzip.decompress(data))['revision'], 7)

    def test_api_rejects_unrelated_host_and_arbitrary_file_paths(self):
        self.assertEqual(self.request('/api/state', host='external.example')[0], 403)
        self.assertEqual(self.request('/../../etc/passwd')[0], 404)


class LaunchDefaultsTests(unittest.TestCase):
    def test_auto_selection_omits_empty_ros_launch_argument(self):
        from live_view_bridge import mapping_command
        args = mapping_command(Path('/repo'))
        self.assertIn('mode:=mapping', args)
        self.assertFalse(any(a.startswith('serial_number:=') for a in args))

    def test_explicit_selection_is_forwarded(self):
        from live_view_bridge import mapping_command
        self.assertIn('serial_number:=TEST_CAMERA', mapping_command(Path('/repo'), 'TEST_CAMERA'))


class DistanceSliceTests(unittest.TestCase):
    def message(self, **changes):
        from types import SimpleNamespace as NS
        msg = NS(width=3, height=2, resolution=.5, origin=NS(x=10., y=20., z=-.8),
                 unknown_value=-1000., data=[0., 1., -1000., -0.1, float('nan'), 2.],
                 header=NS(frame_id='odom', stamp=NS(sec=1, nanosec=0)))
        for key, value in changes.items(): setattr(msg, key, value)
        return msg

    def test_row_major_cell_centers_unknown_and_negative_distance(self):
        from live_layers import slice_snapshot
        snap = slice_snapshot(self.message())
        values = array('f'); values.frombytes(base64.b64decode(snap['xyzd']))
        self.assertEqual(snap['count'], 4)
        self.assertEqual(list(values[:2]), [10.25, 20.25])
        self.assertEqual(list(values[8:10]), [10.25, 20.75])
        self.assertAlmostEqual(values[11], -.1)
        self.assertEqual(list(values[12:14]), [11.25, 20.75])

    def test_bad_frame_shape_and_resolution_are_rejected(self):
        from live_layers import slice_snapshot
        for msg in [self.message(width=4), self.message(resolution=0)]:
            with self.assertRaises(ValueError): slice_snapshot(msg)
        msg = self.message(); msg.header.frame_id = 'map'
        with self.assertRaises(ValueError): slice_snapshot(msg)

    def test_display_budget_samples_without_inventing_unknown_cells(self):
        from live_layers import slice_snapshot
        msg = self.message(width=100, height=100, data=[-1000.] * 10000)
        snap = slice_snapshot(msg, max_cells=100)
        self.assertEqual(snap['stride'], 10)
        self.assertEqual(snap['count'], 0)
        skinny = self.message(width=1, height=10000, data=[1.] * 10000)
        self.assertLessEqual(slice_snapshot(skinny, max_cells=100)['count'], 100)


class LayerApiTests(LiveApiTests):
    def test_layers_survive_meta_only_update_and_stopping(self):
        self.latest.update({'meta': {'running': True}, 'layers': {'sequence': 9, 'color': {'stamp': 1}}})
        self.latest.update({'meta': {'running': False}})
        status, data = self.request('/api/layers')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(gzip.decompress(data))['sequence'], 9)


if __name__ == '__main__':
    unittest.main()

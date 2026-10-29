"""Image conversion checks, also runnable in the camera container."""
import base64
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from live_layers import image_snapshot
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = np = None


@unittest.skipIf(cv2 is None, 'Requires camera-container NumPy/OpenCV')
class ImagePreviewTests(unittest.TestCase):
    def message(self, pixels, encoding, padding=0, endian=False):
        h, w = pixels.shape[:2]
        rows = [row.tobytes()+b'\xff'*padding for row in pixels]
        return NS(width=w, height=h, step=len(rows[0]), data=b''.join(rows),
                  encoding=encoding, is_bigendian=endian,
                  header=NS(frame_id='optical', stamp=NS(sec=123, nanosec=400000000)))

    def decode(self, result):
        return cv2.imdecode(np.frombuffer(base64.b64decode(result['jpeg']), dtype=np.uint8), cv2.IMREAD_UNCHANGED)

    def test_rgb_channel_order_stride_and_capture_timestamp(self):
        pixels=np.zeros((32,32,3),dtype=np.uint8);pixels[:,:,0]=255
        result=image_snapshot(self.message(pixels,'rgb8',padding=8),'color')
        image=self.decode(result)
        self.assertGreater(image[:,:,2].mean(),240)
        self.assertLess(image[:,:,:2].mean(),10)
        self.assertEqual(result['stamp'],123.4)

    def test_big_endian_depth_units_invalid_and_fixed_scale(self):
        pixels=np.zeros((32,96),dtype='>u2');pixels[:,32:64]=200;pixels[:,64:]=5000
        result=image_snapshot(self.message(pixels,'16UC1',padding=4,endian=True),'depth')
        image=self.decode(result)
        self.assertLess(image[:,:24].mean(),5)
        self.assertGreater(image[:,40:56].mean(),245)
        self.assertTrue(10 < image[:,72:88].mean() < 25)
        self.assertEqual(result['depth_range_m'],[.2,5.])

    def test_float_depth_nan_and_bad_stride(self):
        pixels=np.full((32,32),np.nan,dtype='<f4')
        image=self.decode(image_snapshot(self.message(pixels,'32FC1'),'depth'))
        self.assertEqual(image.max(),0)
        msg=self.message(pixels,'32FC1');msg.step=1
        with self.assertRaises(ValueError):image_snapshot(msg,'depth')

if __name__ == '__main__':
    unittest.main()

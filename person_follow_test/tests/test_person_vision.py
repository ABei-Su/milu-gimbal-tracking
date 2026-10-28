"""Execute the real worker against a one-frame SDK fake."""

import queue
import types
import unittest
from unittest.mock import Mock, patch
from milu.settings import Settings
from milu.vision import worker


class VisionTests(unittest.TestCase):
    def execute(self, labels):
        frame = types.SimpleNamespace(width=lambda: 640, height=lambda: 480)
        # Person is deliberately not class 0, proving lookup follows SDK labels.
        objects = [
            types.SimpleNamespace(class_id=i, x=100 + i * 100, y=100, w=80, h=200, score=0.9)
            for i in range(2)
        ]
        detector = types.SimpleNamespace(
            labels=labels,
            input_width=lambda: 640,
            input_height=lambda: 480,
            input_format=lambda: 0,
            detect=lambda *a, **kw: objects,
        )
        cam = Mock()
        cam.read.return_value = frame
        sdk = types.SimpleNamespace(
            camera=types.SimpleNamespace(Camera=lambda *a: cam),
            display=None,
            image=None,
            nn=types.SimpleNamespace(YOLO11=lambda **kw: detector),
            app=types.SimpleNamespace(need_exit=lambda: False),
        )
        stop = Mock()
        stop.is_set.side_effect = [False, True]
        channel = queue.Queue(maxsize=1)
        with (
            patch.dict("sys.modules", {"maix": sdk}),
            patch("milu.maixcam2.check_board"),
            patch("milu.maixcam2.release_default_listener") as release,
            patch("milu.maixcam2.verify_model", return_value="test.mud"),
        ):
            worker(Settings(show_display=False), "test.mud", channel, stop)
        release.assert_called_once_with()
        return channel.get_nowait(), cam

    def test_only_person_is_emitted_and_camera_closes(self):
        result, cam = self.execute(["car", "person"])
        self.assertEqual(result["kind"], "frame")
        self.assertEqual(len(result["detections"]), 1)
        self.assertEqual(result["detections"][0].x1, 200)
        cam.close.assert_called_once()

    def test_deer_model_is_rejected(self):
        result, cam = self.execute(["milu"])
        self.assertEqual(result["kind"], "error")
        self.assertIn("person", result["message"])
        cam.read.assert_not_called()

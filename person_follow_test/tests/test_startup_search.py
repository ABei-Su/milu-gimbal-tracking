import unittest
from dataclasses import replace
from milu.settings import Settings
from milu.gimbal import Gimbal, GimbalState
from test_device import Clock, FakeTransport


class SearchTests(unittest.TestCase):
    def test_found_mid_lift_holds_measured_pose(self):
        clock, bus = Clock(), FakeTransport()
        g = Gimbal(bus, replace(Settings(), startup_pitch_lift=60, home_rate=6), clock, clock.sleep)
        g.start(acquired=lambda: bus.positions[2] <= -120)
        self.assertEqual(g.state, GimbalState.READY)
        self.assertGreater(g.zero[1], -20)
        self.assertLessEqual(g.zero[1], -12)
        self.assertEqual(g.zero[0], 12)
        self.assertEqual(bus.positions[2], round(g.zero[1] * 10))

    def test_face_already_present_does_not_lift(self):
        clock, bus = Clock(), FakeTransport()
        g = Gimbal(bus, replace(Settings(), startup_pitch_lift=60), clock, clock.sleep)
        g.start(acquired=lambda: True)
        self.assertEqual(g.zero, (12, -7))

    def test_detector_failure_faults_and_disables(self):
        clock, bus = Clock(), FakeTransport()
        g = Gimbal(bus, replace(Settings(), startup_pitch_lift=60), clock, clock.sleep)

        def broken():
            raise RuntimeError("vision failed")

        with self.assertRaisesRegex(RuntimeError, "vision failed"):
            g.start(acquired=broken)
        self.assertEqual(g.state, GimbalState.FAULT)
        self.assertEqual([f[2] for f in bus.frames[-2:]], [5, 5])


class VisionAcquisitionTests(unittest.TestCase):
    def test_weak_stale_frames_do_not_stop_search(self):
        import queue
        from types import SimpleNamespace
        from milu.startup_search import StartupSearch
        from test_device import target

        clock = Clock()
        clock.now = 2
        channel = queue.Queue()
        search = StartupSearch(Settings(), channel, SimpleNamespace(is_alive=lambda: True), clock)
        for captured, score in ((1, 0.9), (2, 0.45)):
            channel.put(
                {
                    "kind": "frame",
                    "captured_at": captured,
                    "detections": [target(captured, score=score)],
                }
            )
            self.assertFalse(search.acquired())
        clock.now = 2.1
        channel.put({"kind": "frame", "captured_at": 2.1, "detections": [target(2.1)]})
        self.assertTrue(search.acquired())
        clock.now = 3
        self.assertFalse(search.acquired())

    def test_wait_cancel_timeout_and_worker_failure(self):
        import queue
        from types import SimpleNamespace
        from milu.startup_search import StartupSearch

        clock = Clock()
        proc = SimpleNamespace(is_alive=lambda: True)
        search = StartupSearch(Settings(), queue.Queue(), proc, clock)
        with self.assertRaises(InterruptedError):
            search.wait_ready(lambda: True, clock.sleep)
        with self.assertRaises(TimeoutError):
            search.wait_ready(lambda: False, clock.sleep)
        self.assertLess(clock(), 45.1)
        proc.is_alive = lambda: False
        with self.assertRaisesRegex(RuntimeError, "VISION_WORKER_EXITED"):
            search.acquired()

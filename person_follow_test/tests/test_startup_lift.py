import unittest
from dataclasses import replace
from milu.settings import Settings
from milu.gimbal import Gimbal, GimbalState
from milu.targeting import VisualServo
from test_device import Clock, FakeTransport, target


class StartupLiftTests(unittest.TestCase):
    def test_lift_decreases_pitch_and_holds_yaw_without_mechanical_query(self):
        clock, bus = Clock(), FakeTransport()
        cfg = replace(Settings(), startup_pitch_lift=10, home_rate=3)
        g = Gimbal(bus, cfg, clock, clock.sleep)
        g.start()
        self.assertEqual(g.state, GimbalState.READY)
        self.assertEqual(g.zero, (12, -17))
        positions = [
            (f[1], int.from_bytes(f[3:7], "big", signed=True)) for f in bus.frames if f[2] == 2
        ]
        self.assertTrue(all(v == 120 for m, v in positions if m == 1))
        pitch = [v for m, v in positions if m == 2]
        self.assertEqual(pitch, sorted(pitch, reverse=True))
        self.assertTrue(all(-170 <= v <= -70 for v in pitch))
        self.assertFalse(any(f[2] == 14 and f[3] == 2 for f in bus.frames))
        self.assertLess(clock(), 7)

    def test_lift_validation(self):
        for value in (-1, 91, float("nan"), True):
            with self.assertRaises(ValueError):
                replace(Settings(), startup_pitch_lift=value)
        with self.assertRaises(ValueError):
            replace(Settings(), startup_pitch_lift=10, home_enabled=True)

    def test_face_above_requests_negative_pitch(self):
        servo = VisualServo(replace(Settings(), pitch_sign=1))
        servo.update(target(1, cy=100), 1, (0, 0), 1)
        aim = servo.update(target(1.05, cy=100), 1.05, (0, 0), 1)
        self.assertLess(aim.pitch, 0)

    def test_45_degree_lift_holds_yaw_and_finishes_before_deadline(self):
        clock, bus = Clock(), FakeTransport()
        cfg = replace(Settings(), startup_pitch_lift=45, home_rate=6)
        g = Gimbal(bus, cfg, clock, clock.sleep)
        g.start()
        self.assertEqual(g.state, GimbalState.READY)
        self.assertEqual(g.zero, (12, -52))
        self.assertLess(clock(), 11)
        self.assertTrue(
            all(
                int.from_bytes(f[3:7], "big", signed=True) == 120
                for f in bus.frames
                if f[1] == 1 and f[2] == 2
            )
        )

    def test_60_degree_lift_keeps_yaw_stationary(self):
        clock, bus = Clock(), FakeTransport()
        cfg = replace(Settings(), startup_pitch_lift=60, home_rate=6)
        g = Gimbal(bus, cfg, clock, clock.sleep)
        g.start()
        self.assertEqual(g.state, GimbalState.READY)
        self.assertEqual(g.zero, (12, -67))
        self.assertLess(clock(), 14)
        self.assertTrue(
            all(
                int.from_bytes(f[3:7], "big", signed=True) == 120
                for f in bus.frames
                if f[1] == 1 and f[2] == 2
            )
        )

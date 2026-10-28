import unittest
from dataclasses import replace
from milu.settings import Settings
from milu.targeting import VisualServo
from test_device import target


class YawResponseTests(unittest.TestCase):
    def test_yaw_faster_pitch_identical(self):
        cfg = Settings(
            yaw_sign=1,
            yaw_limit=90,
            pitch_limit=90,
            gain=3.6,
            max_rate=42,
            max_accel=240,
            max_jerk=4000,
            max_lead=5,
            velocity_tau=0.05,
        )
        old = VisualServo(cfg)
        new = VisualServo(replace(cfg, yaw_gain_multiplier=1.3))
        a = b = None
        for i in range(50):
            now = i * 0.02
            frame = target(now, cx=360, cy=270)
            a = old.update(frame, now, (a.yaw, a.pitch) if a else (0, 0), 1)
            b = new.update(frame, now, (b.yaw, b.pitch) if b else (0, 0), 1)
            self.assertEqual(a.pitch, b.pitch)
            self.assertEqual(old.velocity[1], new.velocity[1])
        self.assertGreater(b.yaw, a.yaw * 1.15)

    def test_invalid_gain_multiplier_rejected(self):
        for value in (0, 3, float("nan"), True):
            with self.assertRaises(ValueError):
                replace(Settings(), yaw_gain_multiplier=value)

    def test_independent_yaw_envelope_faster_pitch_unchanged(self):
        cfg = Settings(
            yaw_sign=1,
            yaw_limit=90,
            pitch_limit=90,
            gain=3.6,
            max_rate=42,
            max_accel=240,
            max_jerk=4000,
            max_lead=5,
            velocity_tau=0.05,
        )
        faster = replace(cfg, yaw_max_rate=60, yaw_max_accel=360, yaw_max_jerk=5000, yaw_max_lead=8)
        old, new = VisualServo(cfg), VisualServo(faster)
        a = b = None
        for i in range(70):
            t = i * 0.02
            frame = target(t, cx=600, cy=300)
            a = old.update(frame, t, (a.yaw, a.pitch) if a else (0, 0), 1)
            b = new.update(frame, t, (b.yaw, b.pitch) if b else (0, 0), 1)
            self.assertEqual(a.pitch, b.pitch)
        self.assertGreater(b.yaw, a.yaw * 1.2)

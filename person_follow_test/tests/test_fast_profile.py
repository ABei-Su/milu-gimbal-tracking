"""Deployment response and smoothness regression, ideal feedback plant."""

import unittest
from pathlib import Path
from milu.settings import load_settings
from milu.targeting import VisualServo
from test_device import target


class FastProfileTests(unittest.TestCase):
    def test_edge_target_accelerates_without_steps_or_unbounded_lead(self):
        cfg = load_settings(Path(__file__).resolve().parents[1] / "config.json")
        servo = VisualServo(cfg)
        measured = (0.0, 0.0)
        dt = 1 / cfg.loop_hz
        old_v = old_a = 0.0
        max_rate = 0.0
        for i in range(int(cfg.loop_hz)):
            now = i * dt
            # Realistic  ~17 Hz vision, control reuses only fresh observations.
            capture = int(now * 17) / 17
            aim = servo.update(target(capture, cx=600), now, measured, 1)
            self.assertLessEqual(
                abs(aim.yaw - measured[0]), (cfg.yaw_max_rate or cfg.max_rate) * dt + 1e-8
            )
            self.assertLessEqual(
                abs(servo.velocity[0] - old_v), (cfg.yaw_max_accel or cfg.max_accel) * dt + 1e-8
            )
            self.assertLessEqual(
                abs(servo.acceleration[0] - old_a), (cfg.yaw_max_jerk or cfg.max_jerk) * dt + 1e-8
            )
            old_v, old_a = servo.velocity[0], servo.acceleration[0]
            max_rate = max(max_rate, abs(old_v))
            measured = (aim.yaw, aim.pitch)
        self.assertGreater(max_rate, 20, "edge following still throttled")
        self.assertGreater(abs(measured[0]), 12, "one-second response too slow")

    def test_blocked_motor_still_has_bounded_reference(self):
        cfg = load_settings(Path(__file__).resolve().parents[1] / "config.json")
        servo = VisualServo(cfg)
        for i in range(200):
            now = i / cfg.loop_hz
            aim = servo.update(target(now, cx=600), now, (0, 0), 1)
            self.assertLessEqual(abs(aim.yaw), (cfg.yaw_max_lead or cfg.max_lead) + 1e-8)

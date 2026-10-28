import unittest
from dataclasses import replace
from pathlib import Path
from milu.settings import load_settings
from milu.targeting import VisualServo
from test_device import target


class GentleYawTests(unittest.TestCase):
    def test_response_improves_without_changing_pitch_or_derivative_bounds(self):
        cfg = load_settings(Path(__file__).resolve().parents[1] / "config.json")
        old = VisualServo(replace(cfg, yaw_gain_multiplier=1.08, yaw_max_lead=6))
        new = VisualServo(cfg)
        ma = mb = (0, 0)
        old_v = old_a = 0
        for i in range(100):
            t = i * 0.02
            capture = int(t * 29.5) / 29.5
            frame = target(capture, cx=600, cy=290)
            a = old.update(frame, t, ma, 1)
            b = new.update(frame, t, mb, 1)
            self.assertEqual(a.pitch, b.pitch)
            self.assertLessEqual(abs(new.velocity[0] - old_v), cfg.max_accel * 0.02 + 1e-7)
            self.assertLessEqual(abs(new.acceleration[0] - old_a), cfg.max_jerk * 0.02 + 1e-7)
            old_v, old_a = new.velocity[0], new.acceleration[0]
            ma, mb = (a.yaw, a.pitch), (b.yaw, b.pitch)
        self.assertGreater(b.yaw, a.yaw * 1.03)

    def test_lagged_quantized_feedback_remains_bounded_and_reverses(self):
        cfg = load_settings(Path(__file__).resolve().parents[1] / "config.json")
        s = VisualServo(cfg)
        m = (0, 0)
        peak = 0
        for i in range(300):
            t = i * 0.02
            a = s.update(target(t, cx=600 if i < 150 else 40), t, m, 1)
            self.assertLessEqual(abs(a.yaw - m[0]), (cfg.yaw_max_lead or cfg.max_lead) + 1e-8)
            self.assertLessEqual(abs(s.velocity[0]), 42)
            m = (round((m[0] + 0.15 * (a.yaw - m[0])) * 10) / 10, a.pitch)
            peak = max(peak, m[0])
        self.assertLess(m[0], peak - 20)
        self.assertLess(s.velocity[0], 0)
        a = s.update(None, 6, m, 1)
        self.assertEqual(s.velocity, [0, 0])
        self.assertFalse(cfg.yaw_limit_enabled)

import unittest
from dataclasses import replace
from milu.settings import Settings
from milu.targeting import VisualServo
from test_device import target


class AxisContinuityTests(unittest.TestCase):
    def test_pitch_feedback_jump_does_not_stop_yaw(self):
        s = VisualServo(replace(Settings(), yaw_sign=1, yaw_limit=90, pitch_limit=90))
        measured = (0, 0)
        for i in range(10):
            a = s.update(target(i * 0.05, cx=500, cy=300), i * 0.05, measured, 1)
            measured = (a.yaw, a.pitch)
        yaw_velocity = s.velocity[0]
        a = s.update(target(0.5, cx=500, cy=300), 0.5, (measured[0], measured[1] + 6), 1)
        self.assertGreater(s.velocity[0], yaw_velocity * 0.5)
        self.assertGreater(a.yaw, measured[0])
        self.assertEqual(a.pitch, measured[1] + 6)
        self.assertEqual(s.velocity[1], 0)
        self.assertEqual(s.rebase_reason, "feedback_discontinuity")

    def test_common_profile_without_yaw_overrides_is_symmetric(self):
        from pathlib import Path
        from milu.settings import load_settings

        c = load_settings(Path(__file__).resolve().parents[1] / "config.json")
        c = replace(
            c,
            yaw_gain_multiplier=1,
            yaw_max_rate=0,
            yaw_max_accel=0,
            yaw_max_jerk=0,
            yaw_max_lead=0,
        )
        s = VisualServo(replace(c, hfov_deg=60, vfov_deg=60))
        m = (0, 0)
        for i in range(60):
            t = i * 0.02
            a = s.update(target(t, cx=448, cy=336), t, m, 1)
            self.assertAlmostEqual(a.yaw, a.pitch)
            m = (a.yaw, a.pitch)

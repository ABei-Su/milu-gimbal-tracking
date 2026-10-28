import unittest
from pathlib import Path
from milu.settings import load_settings
from milu.targeting import VisualServo


class RollbackProfileTests(unittest.TestCase):
    def test_restore_pre_request_filter_profile(self):
        cfg = load_settings(Path(__file__).resolve().parents[1] / "config.json")
        self.assertEqual((cfg.yaw_limit, cfg.pitch_limit, cfg.startup_pitch_lift), (90, 90, 60))
        self.assertEqual((cfg.max_rate, cfg.max_accel, cfg.max_jerk), (42, 180, 2400))
        self.assertEqual(
            (cfg.velocity_tau, cfg.smoothing_tau, cfg.prediction_horizon), (0.07, 0.025, 0.03)
        )
        self.assertTrue(cfg.search_during_lift)
        self.assertFalse(hasattr(VisualServo(cfg), "drive_rate"))

"""Motion invariants and fault/recovery tests for the board servo."""

import math
import random
import unittest
from dataclasses import replace
from milu.settings import Settings
from milu.targeting import VisualServo
from test_device import target
from tools.benchmark_servo import run, SCENARIOS
from tools.servo_v020 import VisualServo as Baseline


class TrajectoryTests(unittest.TestCase):
    def test_reused_frame_does_not_refilter(self):
        servo = VisualServo(Settings())
        servo.update(target(0, 400), 0, (0, 0), 1)
        frame = target(0.1, 500)
        servo.update(frame, 0.1, (0, 0), 1)
        filtered = servo.filtered
        servo.update(frame, 0.15, (0, 0), 1)
        self.assertEqual(servo.filtered, filtered)

    def test_jittered_period_bounds_velocity_acceleration_and_jerk(self):
        cfg = Settings(yaw_limit=40, pitch_limit=40)
        servo = VisualServo(cfg)
        measured, previous = [0.0, 0.0], None
        now = 0.0
        rng = random.Random(84)
        for i in range(500):
            dt = rng.choice((0.02, 0.035, 0.05, 0.075))
            now += dt
            aim = servo.update(
                target(now, 320 + 80 * math.sin(now), 240 + 50 * math.sin(0.7 * now)),
                now,
                measured,
                1,
            )
            if previous and not aim.limited and servo.rebase_reason is None:
                old_ref, old_v, old_a = previous
                for k, current in enumerate((aim.yaw, aim.pitch)):
                    self.assertLessEqual(abs(current - old_ref[k]), cfg.max_rate * dt + 1e-8)
                    self.assertLessEqual(abs(servo.velocity[k]), cfg.max_rate + 1e-8)
                    self.assertLessEqual(
                        abs(servo.velocity[k] - old_v[k]), cfg.max_accel * dt + 1e-8
                    )
                    self.assertLessEqual(abs(servo.acceleration[k]), cfg.max_accel + 1e-8)
                    self.assertLessEqual(
                        abs(servo.acceleration[k] - old_a[k]), cfg.max_jerk * dt + 1e-8
                    )
            previous = ((aim.yaw, aim.pitch), list(servo.velocity), list(servo.acceleration))
            measured = [round(aim.yaw * 10) / 10, round(aim.pitch * 10) / 10]

    def test_feedback_blocked_has_no_unbounded_reference(self):
        cfg = Settings()
        servo = VisualServo(cfg)
        for i in range(500):
            aim = servo.update(target(i * 0.05, 600), i * 0.05, (0, 0), 1)
            self.assertLessEqual(abs(aim.yaw), cfg.max_lead + 1e-8)
        self.assertLess(abs(servo.velocity[0]), 0.01)
        # Lost image revokes the outstanding reference, even at a blocked motor.
        aim = servo.update(None, 25, (0, 0), 1)
        self.assertEqual((aim.yaw, aim.pitch), (0, 0))
        self.assertEqual(servo.velocity, [0, 0])

    def test_generation_switch_rebases_reference(self):
        servo = VisualServo(Settings())
        for i in range(8):
            servo.update(target(i * 0.05, 500), i * 0.05, (0, 0), 1)
        aim = servo.update(target(0.4, 100), 0.4, (0.1, 0), 2)
        self.assertEqual((aim.yaw, aim.pitch), (0.1, 0))
        self.assertEqual(servo.velocity, [0, 0])
        self.assertEqual(servo.rebase_reason, "target_changed")

    def test_stale_reordered_and_recovery(self):
        servo = VisualServo(Settings())
        servo.update(target(0, 500), 0, (0, 0), 1)
        servo.update(target(0.1, 500), 0.1, (0, 0), 1)
        aim = servo.update(target(0.05, 100), 0.15, (0.1, 0.2), 1)
        self.assertEqual((aim.yaw, aim.pitch), (0.1, 0.2))
        self.assertEqual(servo.rebase_reason, "out_of_order")
        aim = servo.update(target(0.2, 500), 0.6, (0.1, 0.2), 1)
        self.assertFalse(aim.centered)
        self.assertEqual(servo.velocity, [0, 0])
        # Resume with fresh input; startup is acceleration limited.
        aim = servo.update(target(0.65, 500), 0.65, (0.1, 0.2), 1)
        self.assertLess(abs(aim.yaw - 0.1), 0.1)

    def test_deadband_hysteresis_does_not_hunt_at_boundary(self):
        cfg = Settings()
        servo = VisualServo(cfg)
        for i in range(100):
            cx = 320 + (cfg.deadband + (0.001 if i % 2 else -0.001)) * 640
            aim = servo.update(target(i * 0.05, cx), i * 0.05, (0, 0), 1)
        self.assertEqual((aim.yaw, aim.pitch), (0, 0))

    def test_centered_is_false_while_braking(self):
        servo = VisualServo(Settings())
        measured = (0, 0)
        for i in range(10):
            aim = servo.update(target(i * 0.05, 500), i * 0.05, measured, 1)
            measured = (aim.yaw, aim.pitch)
        aim = servo.update(target(0.5), 0.5, measured, 1)
        self.assertFalse(aim.centered)
        self.assertGreater(abs(servo.velocity[0]), 0.25)

    def test_feedback_jump_and_overshoot_are_bounded(self):
        servo = VisualServo(Settings())
        servo.update(target(0, 500), 0, (0, 0), 1)
        aim = servo.update(target(0.05, 500), 0.05, (5, 0), 1)
        self.assertEqual(aim.yaw, 5)
        self.assertTrue(aim.limited)
        self.assertEqual(servo.rebase_reason, "feedback_discontinuity")
        aim = servo.update(None, 0.1, (10.2, -10.2), 1)
        self.assertEqual((aim.yaw, aim.pitch), (10, -10))
        self.assertTrue(aim.limited)

    def test_settings_validation_and_old_config_compatibility(self):
        from milu.settings import load_settings
        from pathlib import Path
        import json
        import tempfile

        for change in (
            {"max_jerk": 0},
            {"max_jerk": math.inf},
            {"velocity_tau": 0},
            {"max_lead": 0},
            {"max_control_gap": 0.5},
            {"deadband_hysteresis": -0.1},
            {"settle_rate": 0},
            {"loop_hz": 5, "max_control_gap": 0.1},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(Settings(), **change)
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "config.json"
            p.write_text(json.dumps({"gain": 1.2, "yaw_sign": -1}), encoding="utf-8")
            cfg = load_settings(p)
            self.assertEqual(cfg.gain, 1.2)
            self.assertEqual(cfg.max_jerk, 400)


class SimulationTests(unittest.TestCase):
    def test_moving_noise_and_latency_across_seeds(self):
        for seed in (7, 42, 123):
            for name in ("moving", "moving_low_fps"):
                with self.subTest(seed=seed, scenario=name):
                    old, _ = run(Baseline, SCENARIOS[name], seed)
                    new, _ = run(VisualServo, SCENARIOS[name], seed)
                    self.assertLess(
                        new["reference_accel_rms_deg_s2"], old["reference_accel_rms_deg_s2"] * 0.4
                    )
                    self.assertLess(new["tracking_rmse_deg"], old["tracking_rmse_deg"])
                    self.assertLess(
                        new["simulated_motor_accel_rms_deg_s2"],
                        old["simulated_motor_accel_rms_deg_s2"],
                    )
                    self.assertLessEqual(new["max_command_deg"], 10)

    def test_limit_reversal_is_smooth_and_bounded(self):
        metrics, _ = run(VisualServo, SCENARIOS["near_limit"])
        self.assertLessEqual(metrics["max_command_deg"], 10)
        self.assertLess(metrics["max_reference_rate_jump_deg_s"], 3)
        self.assertLess(metrics["final_error_deg"], 1)


if __name__ == "__main__":
    unittest.main()

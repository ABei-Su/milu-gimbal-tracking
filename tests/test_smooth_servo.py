"""Regressions for visible quantization stalls and abrupt setpoint stops."""

import unittest
from milu.settings import Settings
from milu.targeting import VisualServo
from test_device import target


class SmoothRegressions(unittest.TestCase):
    def test_sub_quantum_velocity_accumulates(self):
        cfg = Settings(gain=0.1, deadband=0.001)
        servo = VisualServo(cfg)
        measured = [0.0, 0.0]
        for i in range(160):
            aim = servo.update(target(i * 0.05, 370), i * 0.05, measured, 1)
            measured = [round(aim.yaw * 10) / 10, round(aim.pitch * 10) / 10]
        self.assertLess(measured[0], -0.5)

    def test_centered_axis_does_not_follow_other_axis(self):
        servo = VisualServo(Settings())
        measured = [0.0, 0.0]
        for i in range(30):
            aim = servo.update(target(i * 0.05, 325, 400), i * 0.05, measured, 1)
            measured = [aim.yaw, aim.pitch]
        self.assertAlmostEqual(aim.yaw, 0.0)
        self.assertGreater(aim.pitch, 0)

    def test_entering_center_does_not_hard_stop(self):
        cfg = Settings()
        servo = VisualServo(cfg)
        measured = [0.0, 0.0]
        for i in range(10):
            aim = servo.update(target(i * 0.05, 500), i * 0.05, measured, 1)
            measured = [aim.yaw, aim.pitch]
        before = servo.velocity[0]
        servo.update(target(0.5), 0.5, measured, 1)
        self.assertLessEqual(abs(servo.velocity[0] - before), cfg.max_accel * 0.05 + 1e-9)

    def test_long_control_gap_rebases_even_with_fresh_frame(self):
        servo = VisualServo(Settings())
        servo.update(target(0, 500), 0, (0, 0), 1)
        servo.update(target(0.05, 500), 0.05, (0, 0), 1)
        aim = servo.update(target(1, 500), 1, (0.2, 0.3), 1)
        self.assertEqual((aim.yaw, aim.pitch), (0.2, 0.3))
        self.assertFalse(aim.centered)


if __name__ == "__main__":
    unittest.main()

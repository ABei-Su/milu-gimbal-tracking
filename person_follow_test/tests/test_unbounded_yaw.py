import unittest
from dataclasses import replace
from milu.settings import Settings
from milu.gimbal import Gimbal
from milu.targeting import VisualServo
from test_device import Clock, FakeTransport, target


class UnboundedYawTests(unittest.TestCase):
    def test_yaw_crosses_old_boundary_both_directions(self):
        for sign in (-1, 1):
            cfg = replace(Settings(), yaw_sign=sign, yaw_limit_enabled=False)
            s = VisualServo(cfg)
            m = (sign * 359, 0)
            for i in range(101):
                t = i * 0.02
                a = s.update(target(t, cx=600), t, m, 1)
                m = (a.yaw, a.pitch)
            self.assertGreater(sign * a.yaw, 365)

    def test_device_accepts_yaw_beyond_one_turn(self):
        clock, bus = Clock(), FakeTransport()
        g = Gimbal(bus, replace(Settings(), yaw_limit_enabled=False), clock, clock.sleep)
        g.start()
        for angle in (-400, 400):
            g.move(angle, 0)
            self.assertAlmostEqual(g.poll()[0], angle)
        with self.assertRaises(ValueError):
            g.move(400, 11)

    def test_old_config_still_bounded(self):
        self.assertTrue(Settings().yaw_limit_enabled)
        with self.assertRaises(ValueError):
            replace(Settings(), yaw_limit_enabled=1)

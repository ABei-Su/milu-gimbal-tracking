import unittest
from milu.settings import Settings
from milu.targeting import VisualServo
from test_device import target


class LossHoldTests(unittest.TestCase):
    def test_sag_does_not_move_hold_setpoint(self):
        s = VisualServo(Settings())
        s.update(target(0), 0, (0, 0), 1)
        a = s.update(None, 0.05, (0, 0.2), 1)
        b = s.update(None, 0.1, (0, 0.7), 1)
        self.assertEqual((a.yaw, a.pitch), (b.yaw, b.pitch))
        c = s.update(target(0.15), 0.15, (0, 0.7), 1)
        self.assertEqual(c.pitch, 0.7)
        self.assertEqual(s.velocity, [0, 0])

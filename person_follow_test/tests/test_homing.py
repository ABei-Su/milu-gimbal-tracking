import unittest
from dataclasses import replace
from functools import reduce
from operator import xor
from milu.homing import home_targets
from milu.gimbal import Gimbal, GimbalState
from milu.settings import Settings
from test_device import Clock, FakeTransport


class HomeBus(FakeTransport):
    def __init__(self):
        super().__init__()
        self.offset = {1: 600, 2: 20}
        self.blocked = False

    def send(self, frame):
        if frame[2] == 2 and self.blocked:
            self.frames.append(frame)
            return
        super().send(frame)
        if frame[2] == 14 and frame[3] == 2:
            motor = frame[1]
            raw = (self.positions[motor] - self.offset[motor]) % 3600
            body = bytes((0x7A, motor, 2)) + raw.to_bytes(4, "big", signed=True)
            self.pending = body + bytes((reduce(xor, body), 0x7B))


class HomingTests(unittest.TestCase):
    def make(self):
        self.clock = Clock()
        self.bus = HomeBus()
        cfg = replace(Settings(), home_enabled=True)
        return Gimbal(self.bus, cfg, self.clock, self.clock.sleep)

    def test_mechanical_zero_is_not_total_zero(self):
        self.assertEqual(home_targets((570, -65), (350, 295), 100), (580, 0))
        with self.assertRaises(ValueError):
            home_targets((0, 0), (180, 0), 100)

    def test_home_reaches_calibrated_origin(self):
        g = self.make()
        g.start()
        self.assertEqual(g.state, GimbalState.READY)
        self.assertEqual(g.zero, (60, 2))
        self.assertAlmostEqual(g.measured[0], 0, delta=0.4)
        self.assertTrue(all(f[2] not in (8, 9, 10, 11, 13) for f in self.bus.frames))

    def test_blocked_home_faults_bounded(self):
        g = self.make()
        self.bus.blocked = True
        with self.assertRaises((ValueError, TimeoutError)):
            g.start()
        self.assertEqual(g.state, GimbalState.FAULT)
        self.assertLess(self.clock(), 35)

    def test_cancel_before_enable(self):
        g = self.make()
        with self.assertRaises(InterruptedError):
            g.start(cancelled=lambda: True)
        self.assertFalse(any(f[2] == 6 for f in self.bus.frames))

    def test_excess_travel_never_enables(self):
        g = self.make()
        self.bus.offset[1] = self.bus.positions[1] - 1800
        with self.assertRaisesRegex(ValueError, "HOME_TRAVEL_EXCEEDED"):
            g.start()
        self.assertFalse(any(f[2] == 6 for f in self.bus.frames))

    def test_cancel_during_home_disables(self):
        g = self.make()
        with self.assertRaises(InterruptedError):
            g.start(cancelled=lambda: self.clock() > 2.0)
        self.assertEqual([f[2] for f in self.bus.frames[-2:]], [5, 5])

    def test_timeout_is_bounded(self):
        g = self.make()
        g.cfg = replace(g.cfg, home_timeout=5, home_rate=1)
        with self.assertRaisesRegex(TimeoutError, "HOME_TIMEOUT"):
            g.start()
        self.assertLess(self.clock(), 7)
        self.assertEqual(g.state, GimbalState.FAULT)

    def test_full_half_turn_and_no_startup_disable(self):
        g = self.make()
        g.cfg = replace(g.cfg, home_max_travel=180, home_timeout=45)
        self.bus.offset[1] = self.bus.positions[1] - 1800
        g.start()
        self.assertEqual(g.state, GimbalState.READY)
        self.assertLess(self.clock(), 45)
        self.assertFalse(any(f[2] == 5 for f in self.bus.frames))

    def test_travel_error_identifies_axis_and_angle(self):
        with self.assertRaisesRegex(ValueError, r"motor=2.*mechanical=180"):
            home_targets((0, 0), (0, 180), 100)

    def test_blocked_axis_error_reports_reference_and_feedback(self):
        g = self.make()
        self.bus.blocked = True
        with self.assertRaisesRegex(
            ValueError, r"HOME_FOLLOWING_ERROR: motor=1.*reference=.*measured=.*error="
        ):
            g.start()
        self.assertEqual([f[2] for f in self.bus.frames[-2:]], [5, 5])

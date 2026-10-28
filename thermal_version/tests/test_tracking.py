import contextlib
import io
import math
import unittest
from dataclasses import replace

from milu.simulate import run
from milu.tracking import Config, Detection, State, Tracker


def target(now, x=320, y=240, confidence=0.9):
    return Detection(x - 5, y - 5, x + 5, y + 5, 640, 480, confidence, now)


class TrackingTests(unittest.TestCase):
    def test_initial_and_first_frame_do_not_jump(self):
        t = Tracker()
        self.assertEqual(t.state, State.IDLE)
        cmd = t.update(target(0, 500), 0)
        self.assertEqual(cmd.yaw_deg, 0)
        self.assertEqual(cmd.state, State.TRACKING)

    def test_directions_and_step_bound(self):
        for sign in (-1, 1):
            t = Tracker(Config(yaw_sign=sign, pitch_sign=sign))
            t.update(target(0), 0)
            cmd = t.update(target(0.05, 600, 400), 0.05)
            self.assertGreater(sign * cmd.yaw_deg, 0)
            self.assertGreater(sign * cmd.pitch_deg, 0)
            self.assertLessEqual(abs(cmd.yaw_deg), 0.4)

    def test_deadband_dwell_and_exit(self):
        t = Tracker()
        for i in range(5):
            cmd = t.update(target(i / 10), i / 10)
        self.assertEqual(cmd.state, State.CENTERED)
        self.assertEqual((cmd.yaw_deg, cmd.pitch_deg), (0, 0))
        self.assertEqual(t.update(target(0.5, 500), 0.5).state, State.TRACKING)

    def test_missing_target_breaks_dwell(self):
        t = Tracker()
        t.update(target(0), 0)
        t.update(target(0.2), 0.2)
        t.update(None, 0.21)
        self.assertEqual(t.update(target(0.4), 0.4).state, State.TRACKING)

    def test_capture_gap_breaks_dwell(self):
        t = Tracker()
        t.update(target(0), 0)
        self.assertEqual(t.update(target(0.4), 0.4).state, State.TRACKING)

    def test_loss_holds_position_and_recovery(self):
        t = Tracker()
        t.update(target(0, 500), 0)
        last = t.update(target(0.1, 500), 0.1)
        self.assertEqual(t.update(None, 0.2).state, State.TRACKING)
        lost = t.update(None, 0.7)
        self.assertEqual(lost.state, State.LOST)
        self.assertEqual(lost.yaw_deg, last.yaw_deg)
        self.assertEqual(t.update(target(0.8), 0.8).state, State.TRACKING)

    def test_empty_session_remains_idle(self):
        self.assertEqual(Tracker().update(None, 100).state, State.IDLE)

    def test_stale_low_confidence_and_duplicate_do_not_move(self):
        for bad in (target(0), target(0.2, 500, confidence=0.1), target(0.1, 500)):
            t = Tracker()
            t.update(target(0.1, 500), 0.1)
            cmd = t.update(bad, 0.3)
            self.assertEqual(cmd.yaw_deg, 0)
            self.assertEqual(cmd.reason, "NO_FRESH_TARGET")

    def test_duplicates_eventually_timeout(self):
        t = Tracker()
        d = target(0)
        t.update(d, 0)
        self.assertEqual(t.update(d, 0.6).state, State.LOST)

    def test_limits_and_no_windup(self):
        t = Tracker(Config(yaw_min=-1, yaw_max=1, pitch_min=-1, pitch_max=1))
        for i in range(100):
            cmd = t.update(target(i / 20, 600, 400), i / 20)
        self.assertEqual((cmd.yaw_deg, cmd.pitch_deg), (1, 1))
        cmd = t.update(target(5, 20, 20), 5)
        self.assertLess(cmd.yaw_deg, 1)
        self.assertLess(cmd.pitch_deg, 1)

    def test_long_pause_caps_step(self):
        t = Tracker()
        t.update(target(0), 0)
        self.assertLessEqual(t.update(target(100, 600), 100).yaw_deg, 0.4)

    def test_invalid_detection_faults_without_movement(self):
        invalid = [
            replace(target(0.1), x1=-1),
            replace(target(0.1), width=0),
            replace(target(0.1), x2=math.nan),
            replace(target(0.1), confidence=2),
            replace(target(0.1), width=640.0),
            target(2),
            "bad",
        ]
        for d in invalid:
            t = Tracker()
            t.update(target(0), 0)
            with self.subTest(d=d), self.assertRaises(ValueError):
                t.update(d, 0.1)
            self.assertEqual(t.state, State.FAULT)
            self.assertEqual(t.fail().yaw_deg, 0)

    def test_invalid_clock_faults(self):
        for now in (-1, 0, math.nan, math.inf, True):
            t = Tracker()
            t.update(None, 0)
            with self.subTest(now=now), self.assertRaises(ValueError):
                t.update(None, now)
            self.assertEqual(t.state, State.FAULT)

    def test_terminal_events_idempotent(self):
        for first, expected in (("stop", State.STOPPED), ("fail", State.FAULT)):
            t = Tracker()
            getattr(t, first)()
            t.stop()
            t.fail()
            self.assertEqual(t.state, expected)
            with self.assertRaises(RuntimeError):
                t.update(target(1), 1)

    def test_bad_configuration_and_position(self):
        for kwargs in (
            {"gain": math.nan},
            {"max_dt": 0},
            {"yaw_sign": 0},
            {"yaw_min": 30},
            {"min_confidence": 2},
            {"deadband": 1},
            {"stale_after": 1},
            {"dwell": -1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Config(**kwargs)
        for yaw in (math.inf, 100):
            with self.assertRaises(ValueError):
                Tracker(yaw=yaw)

    def test_light_always_off(self):
        t = Tracker()
        for i in range(20):
            self.assertFalse(t.update(target(i / 10), i / 10).light_on)
        self.assertFalse(t.stop().light_on)

    def test_ideal_closed_loop_converges_and_loses_target(self):
        with contextlib.redirect_stdout(io.StringIO()):
            yaw_error, pitch_error, state = run()
        self.assertLess(abs(yaw_error), 1)
        self.assertLess(abs(pitch_error), 1)
        self.assertEqual(state, State.LOST)

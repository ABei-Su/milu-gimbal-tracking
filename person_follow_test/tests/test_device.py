"""Deterministic fake-UART integration tests; no physical devices."""

import math
import unittest
from functools import reduce
from operator import xor

from milu import f32c
from milu.gimbal import Gimbal, GimbalState
from milu.runtime import light_eligible
from milu.settings import Settings
from milu.targeting import TargetSelector, TargetStream, VisualServo
from milu.tracking import Detection


def target(t, cx=320, cy=240, score=0.95):
    return Detection(cx - 10, cy - 10, cx + 10, cy + 10, 640, 480, score, t)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, value):
        self.now += value


class FakeTransport:
    def __init__(self):
        self.frames = []
        self.pending = b""
        self.positions = {1: 120, 2: -70}
        self.missing = None
        self.fail_position = None
        self.closed = False

    def send(self, frame):
        self.frames.append(frame)
        motor, command = frame[1:3]
        if command == 2:
            if self.fail_position == motor:
                raise OSError("injected partial write")
            self.positions[motor] = int.from_bytes(frame[3:7], "big", signed=True)
        elif command == 14 and motor != self.missing:
            body = bytes((0x7A, motor, 1)) + self.positions[motor].to_bytes(4, "big", signed=True)
            self.pending = body + bytes((reduce(xor, body), 0x7B))

    def read(self):
        chunk, self.pending = self.pending[:2], self.pending[2:]
        return chunk

    def clear_input(self):
        self.pending = b""

    def close(self):
        self.closed = True


class GimbalTests(unittest.TestCase):
    def create(self):
        self.clock, self.bus = Clock(), FakeTransport()
        self.gimbal = Gimbal(self.bus, Settings(), self.clock, self.clock.sleep)
        return self.gimbal

    def test_capture_existing_position_without_zero_jump(self):
        g = self.create()
        g.start()
        self.assertEqual(g.zero, (12, -7))
        self.assertEqual(g.state, GimbalState.READY)
        self.assertEqual(g.poll(), (0, 0))
        self.assertEqual(self.bus.positions, {1: 120, 2: -70})
        self.assertIn(f32c.mode(1, 3), self.bus.frames)
        self.assertIn(f32c.speed(2, 30), self.bus.frames)

    def test_relative_motion_and_feedback(self):
        g = self.create()
        g.start()
        g.move(-2, 1)
        self.assertEqual(g.poll(), (-2, 1))

    def test_invalid_second_axis_sends_no_first_position(self):
        g = self.create()
        g.start()
        n = len(self.bus.frames)
        with self.assertRaises(ValueError):
            g.move(1, 100)
        self.assertFalse(any(f[2] == 2 for f in self.bus.frames[n:]))
        self.assertEqual(g.state, GimbalState.FAULT)
        self.assertIn(f32c.disable(1), self.bus.frames[n:])
        self.assertIn(f32c.disable(2), self.bus.frames[n:])

    def test_missing_feedback_is_bounded_and_faults(self):
        g = self.create()
        g.start()
        self.bus.missing = 2
        before = self.clock()
        with self.assertRaises(TimeoutError):
            g.poll()
        self.assertLess(self.clock() - before, 0.2)
        self.assertEqual(g.state, GimbalState.FAULT)

    def test_failure_of_second_axis_disables_both(self):
        g = self.create()
        g.start()
        self.bus.fail_position = 2
        with self.assertRaises(OSError):
            g.move(1, 1)
        self.assertEqual(self.bus.frames[-2:], [f32c.disable(1), f32c.disable(2)])

    def test_startup_failure_does_not_become_ready(self):
        g = self.create()
        self.bus.missing = 1
        with self.assertRaises(TimeoutError):
            g.start()
        self.assertEqual(g.state, GimbalState.FAULT)
        with self.assertRaises(RuntimeError):
            g.start()

    def test_stale_feedback_rejects_motion(self):
        g = self.create()
        g.start()
        self.clock.sleep(0.6)
        with self.assertRaises(TimeoutError):
            g.move(0, 0)

    def test_feedback_outside_limits_faults(self):
        g = self.create()
        g.start()
        self.bus.positions[1] += 110
        with self.assertRaises(ValueError):
            g.poll()

    def test_close_is_idempotent_and_terminal(self):
        g = self.create()
        g.start()
        g.close()
        n = len(self.bus.frames)
        g.close()
        self.assertEqual(len(self.bus.frames), n)
        self.assertTrue(self.bus.closed)
        with self.assertRaises(RuntimeError):
            g.move(0, 0)

    def test_nonfinite_commands_fault(self):
        g = self.create()
        g.start()
        with self.assertRaises(ValueError):
            g.move(math.nan, 0)

    def test_start_twice_rejected(self):
        g = self.create()
        g.start()
        with self.assertRaises(RuntimeError):
            g.start()


class SelectorTests(unittest.TestCase):
    def test_locks_existing_target_over_higher_confidence_new_target(self):
        s = TargetSelector(Settings())
        original, _ = s.select([target(0, 180)], 0, 0)
        chosen, ambiguous = s.select([target(0.1, 190, score=0.7), target(0.1, 550)], 0.1, 0.1)
        self.assertLess(chosen.x1, 200)
        self.assertTrue(ambiguous)  # tracking continues, light stays off with multiple candidates
        self.assertEqual(s.generation, 1)
        self.assertIsNotNone(original)

    def test_jump_rejected_until_lock_expires(self):
        s = TargetSelector(Settings())
        s.select([target(0, 100)], 0, 0)
        self.assertIsNone(s.select([target(0.1, 550)], 0.1, 0.1)[0])
        self.assertIsNotNone(s.select([target(0.7, 550)], 0.7, 0.7)[0])
        self.assertEqual(s.generation, 2)

    def test_duplicate_old_and_stale_frames_rejected(self):
        s = TargetSelector(Settings())
        s.select([target(0)], 0, 0)
        self.assertIsNone(s.select([target(0)], 0, 0.1)[0])
        self.assertIsNone(s.select([target(0.1)], 0.1, 0.5)[0])

    def test_confidence_and_ambiguity(self):
        s = TargetSelector(Settings())
        self.assertIsNone(s.select([target(0, score=0.2)], 0, 0)[0])
        self.assertTrue(s.select([target(0.1), target(0.1, 350)], 0.1, 0.1)[1])

    def test_future_or_mixed_frames_fail(self):
        s = TargetSelector(Settings())
        with self.assertRaises(ValueError):
            s.select([target(2)], 2, 1)
        with self.assertRaises(ValueError):
            s.select([target(0)], 0.1, 0.1)


class ServoTests(unittest.TestCase):
    def test_vendor_direction_and_acceleration_limit(self):
        servo = VisualServo(Settings())
        servo.update(target(0, 500, 400), 0, (0, 0), 1)
        aim = servo.update(target(0.05, 500, 400), 0.05, (0, 0), 1)
        self.assertLess(aim.yaw, 0)
        self.assertGreater(aim.pitch, 0)
        self.assertLessEqual(abs(aim.yaw), 60 * 0.05**2 + 1e-9)

    def test_no_target_holds_measured_not_unreached_goal(self):
        servo = VisualServo(Settings())
        aim = servo.update(None, 0, (2, 3), 0)
        self.assertEqual((aim.yaw, aim.pitch), (2, 3))
        self.assertFalse(aim.centered)

    def test_deadband_and_aim_offset(self):
        cfg = Settings(aim_x=0.6)
        aim = VisualServo(cfg).update(target(0, 384), 0, (1, 2), 1)
        self.assertTrue(aim.centered)
        self.assertEqual((aim.yaw, aim.pitch), (1, 2))

    def test_saturation_and_stale_input(self):
        s = VisualServo(Settings())
        s.update(target(0, 630), 0, (-10, 0), 1)
        aim = s.update(target(0.1, 630), 0.1, (-10, 0), 1)
        self.assertTrue(aim.limited)
        self.assertEqual(aim.yaw, -10)
        aim = s.update(target(0.1), 1, (-10, 0), 1)
        self.assertFalse(aim.centered)

    def test_clock_and_nan_rejected(self):
        s = VisualServo(Settings())
        s.update(None, 0, (0, 0), 0)
        with self.assertRaises(ValueError):
            s.update(None, 0, (0, 0), 0)
        with self.assertRaises(ValueError):
            VisualServo(Settings()).update(None, 0, (math.nan, 0), 0)

    def test_closed_loop_convergence_with_vendor_sign(self):
        cfg = Settings()
        servo = VisualServo(cfg)
        measured = [0.0, 0.0]
        for i in range(240):
            t = i * 0.05
            ex = math.tan(math.radians(5 - cfg.yaw_sign * measured[0])) / (
                2 * math.tan(math.radians(cfg.hfov_deg / 2))
            )
            ey = math.tan(math.radians(-3 - cfg.pitch_sign * measured[1])) / (
                2 * math.tan(math.radians(cfg.vfov_deg / 2))
            )
            aim = servo.update(target(t, 640 * (0.5 + ex), 480 * (0.5 + ey)), t, measured, 1)
            measured = [aim.yaw, aim.pitch]
        self.assertLess(abs(5 - cfg.yaw_sign * measured[0]), 1.5)
        self.assertLess(abs(-3 - cfg.pitch_sign * measured[1]), 1.2)


class LightTests(unittest.TestCase):
    def test_person_mode_never_grants_light(self):
        self.assertFalse(light_eligible(None, None, None, False, None, None, 0))


class SettingsTests(unittest.TestCase):
    def test_invalid_settings(self):
        for kwargs in (
            {"gain": math.nan},
            {"yaw_limit": 100},
            {"laser_active_high": 1},
            {"position_rpm": 1.5},
            {"laser_pin": "B0"},
            {"paper_roi": [1, 0, 0, 1]},
            {"query_timeout": 1},
            {"laser_pulse": 10},
            {"hfov_deg": 180},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Settings(**kwargs)


class FrameStreamTests(unittest.TestCase):
    def test_low_fps_holds_only_fresh_measurements(self):
        stream = TargetStream(Settings())
        message = {"captured_at": 0, "detections": [target(0)]}
        self.assertIsNotNone(stream.update(message, 0)[0])
        self.assertIsNotNone(stream.update(None, 0.05)[0])
        self.assertIsNone(stream.update(None, 0.26)[0])

    def test_explicit_empty_frame_immediately_clears_target(self):
        stream = TargetStream(Settings())
        stream.update({"captured_at": 0, "detections": [target(0)]}, 0)
        self.assertIsNone(stream.update({"captured_at": 0.1, "detections": []}, 0.1)[0])

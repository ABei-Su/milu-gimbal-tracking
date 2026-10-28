"""End-to-end orchestration against deterministic board/vision fakes."""

import json
import queue
import tempfile
import types
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from milu import runtime
from milu.gimbal import Gimbal
from milu.settings import Settings
from test_device import Clock, FakeTransport, target


class Event:
    def __init__(self):
        self.value = False

    def set(self):
        self.value = True

    def is_set(self):
        return self.value


class Process:
    pid = None

    def start(self):
        self.pid = 123
        self.alive = True

    def is_alive(self):
        return self.alive

    def join(self, timeout):
        self.alive = False

    def terminate(self):
        self.alive = False


class Channel:
    def __init__(self, clock, fail=False, empty=False):
        self.clock, self.fail, self.empty = clock, fail, empty
        self.count = 0
        self.last_capture = -1

    def get_nowait(self):
        self.count += 1
        if self.fail and self.count > 5:
            return {"kind": "error", "message": "injected inference failure"}
        # Simulate camera at 10 FPS while controller runs at 20 Hz.
        if self.clock() - self.last_capture < 0.1:
            raise queue.Empty
        self.last_capture = self.clock()
        return {
            "kind": "frame",
            "captured_at": self.clock(),
            "detections": [] if self.empty else [target(self.clock())],
            "latency": 0,
        }

    def close(self):
        pass


class Output:
    def __init__(self):
        self.values = []

    def set(self, value):
        self.values.append(value)


class RuntimeTests(unittest.TestCase):
    def execute(self, mode, fail=False, empty=False):
        from milu import maixcam2

        clock, bus, light = Clock(), FakeTransport(), Output()
        channel = Channel(clock, fail, empty)
        process = Process()
        context = types.SimpleNamespace(
            Queue=lambda **kw: channel, Event=Event, Process=lambda **kw: process
        )
        fake_maix = types.SimpleNamespace(app=types.SimpleNamespace(need_exit=lambda: clock() > 4))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(asdict(Settings())), encoding="utf-8")
            with (
                patch.dict("sys.modules", {"maix": fake_maix}),
                patch.object(maixcam2, "check_board"),
                patch.object(maixcam2, "verify_model", return_value="fake.mud"),
                patch.object(maixcam2, "SerialTransport", return_value=bus) as serial_factory,
                patch.object(maixcam2, "LaserOutput", return_value=light) as light_factory,
                patch.object(runtime.mp, "get_context", return_value=context),
                patch.object(runtime.time, "monotonic", clock),
                patch.object(runtime.time, "sleep", clock.sleep),
                patch.object(
                    runtime,
                    "Gimbal",
                    side_effect=lambda port, cfg: Gimbal(port, cfg, clock, clock.sleep),
                ),
            ):
                if fail:
                    with self.assertRaisesRegex(RuntimeError, "injected inference"):
                        runtime.run(path, mode)
                else:
                    runtime.run(path, mode)
                if mode == "observe":
                    serial_factory.assert_not_called()
                    light_factory.assert_not_called()
        return bus, light

    def test_observe_does_not_open_actuator_devices(self):
        bus, light = self.execute("observe")
        self.assertEqual(bus.frames, [])
        self.assertEqual(light.values, [])

    def test_paper_mode_reaches_light_pulse_at_lower_camera_fps(self):
        bus, light = self.execute("paper")
        self.assertIn(True, light.values)
        self.assertFalse(light.values[-1])
        self.assertTrue(bus.closed)

    def test_track_mode_never_turns_light_on(self):
        _, light = self.execute("track")
        self.assertNotIn(True, light.values)

    def test_worker_failure_closes_devices_and_light(self):
        bus, light = self.execute("paper", fail=True)
        self.assertFalse(light.values[-1])
        self.assertTrue(bus.closed)
        self.assertEqual([f[2] for f in bus.frames[-2:]], [5, 5])

    def test_no_detection_never_enables_light(self):
        _, light = self.execute("paper", empty=True)
        self.assertNotIn(True, light.values)

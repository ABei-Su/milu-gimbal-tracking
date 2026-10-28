"""End-to-end orchestration against deterministic board/vision fakes."""

import json
import queue
import tempfile
import types
import unittest
from dataclasses import asdict, replace
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
    def execute(self, mode, fail=False, empty=False, search=False):
        from milu import maixcam2

        clock, bus, light = Clock(), FakeTransport(), Output()
        channel = Channel(clock, fail, empty)
        events = []
        original_get = channel.get_nowait

        def receive_after_poll():
            if mode == "track" and (not search or "ready" in events):
                self.assertTrue(events and events[-1] == "poll")
            events.append("receive")
            return original_get()

        channel.get_nowait = receive_after_poll

        class OrderedGimbal(Gimbal):
            def start(self, **kwargs):
                super().start(**kwargs)
                events.append("ready")

            def poll(self):
                result = super().poll()
                events.append("poll")
                return result

        process = Process()
        original_start = process.start

        def start_after_actuators():
            if mode == "track":
                if search:
                    self.assertEqual(bus.frames, [])
                else:
                    self.assertTrue(any(f[2] == 6 for f in bus.frames))
            original_start()

        process.start = start_after_actuators
        context = types.SimpleNamespace(
            Queue=lambda **kw: channel, Event=Event, Process=lambda **kw: process
        )
        fake_maix = types.SimpleNamespace(app=types.SimpleNamespace(need_exit=lambda: clock() > 4))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            cfg = (
                replace(Settings(), search_during_lift=True, startup_pitch_lift=60)
                if search
                else Settings()
            )
            path.write_text(json.dumps(asdict(cfg)), encoding="utf-8")
            with (
                patch.dict("sys.modules", {"maix": fake_maix}),
                patch.object(maixcam2, "check_board"),
                patch.object(maixcam2, "release_default_listener") as release,
                patch.object(maixcam2, "verify_model", return_value="fake.mud"),
                patch.object(maixcam2, "SerialTransport", return_value=bus) as serial_factory,
                patch.object(maixcam2, "LaserOutput", return_value=light) as light_factory,
                patch.object(runtime.mp, "get_context", return_value=context),
                patch.object(runtime.time, "monotonic", clock),
                patch.object(runtime.time, "sleep", clock.sleep),
                patch.object(
                    runtime,
                    "Gimbal",
                    side_effect=lambda port, cfg: OrderedGimbal(port, cfg, clock, clock.sleep),
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
                release.assert_called_once_with()
        return bus, light

    def test_observe_does_not_open_actuator_devices(self):
        bus, light = self.execute("observe")
        self.assertEqual(bus.frames, [])
        self.assertEqual(light.values, [])

    def test_paper_mode_rejected_before_hardware_access(self):
        with self.assertRaises(ValueError):
            runtime.run("nonexistent.json", "paper")

    def test_track_mode_never_turns_light_on(self):
        _, light = self.execute("track")
        self.assertNotIn(True, light.values)

    def test_worker_failure_closes_devices_and_light(self):
        bus, light = self.execute("track", fail=True)
        self.assertFalse(light.values[-1])
        self.assertTrue(bus.closed)
        self.assertEqual([f[2] for f in bus.frames[-2:]], [5, 5])

    def test_no_detection_never_enables_light(self):
        _, light = self.execute("track", empty=True)
        self.assertNotIn(True, light.values)

    def test_search_starts_camera_first_and_face_prevents_full_lift(self):
        bus, _ = self.execute("track", search=True)
        pitch = [
            int.from_bytes(f[3:7], "big", signed=True)
            for f in bus.frames
            if f[1] == 2 and f[2] == 2
        ]
        self.assertTrue(all(v == -70 for v in pitch))

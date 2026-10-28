"""Thermal integration against deterministic I/O and process fakes."""

from contextlib import ExitStack
from dataclasses import asdict
import json
from pathlib import Path
import queue
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from milu.gimbal import Gimbal
from milu.settings import Settings
from thermo import runtime, sensor
from thermo.config import ThermalConfig
from thermo.preflight import inspect
from test_device import Clock, FakeTransport
from test_runtime import Event, Output, Process
from test_thermal import matrix, target


class Queue:
    def __init__(self, source=None):
        self.source = source
        self.items = []
        self.closed = False

    def get_nowait(self):
        if self.source:
            return self.source()
        if not self.items:
            raise queue.Empty
        return self.items.pop(0)

    def put_nowait(self, value):
        self.items.append(value)

    def cancel_join_thread(self):
        pass

    def close(self):
        self.closed = True


class IntegrationTests(unittest.TestCase):
    def execute(self, *, failure=False, pending=False, motion=True, dropout=False):
        clock, bus, light = Clock(), FakeTransport(), Output()
        cfg = ThermalConfig(
            sensor_backend="pending_uart" if pending else "mlx90640_i2c",
            sensor_confirmed=not pending,
            alignment_confirmed=True,
            stabilization=0.1,
        )

        def frame():
            if failure and clock() > 2:
                return {"kind": "error", "message": "injected UI failure"}
            return {
                "kind": "frame",
                "captured_at": clock(),
                "target": target(clock()),
                "session": 1,
                "motion": motion,
                "state": "TRACKING",
            }

        def sample():
            if pending or (dropout and clock() > 3):
                raise queue.Empty
            return {"kind": "thermal", "captured_at": clock(), "matrix": matrix()}

        frames, statuses, temperatures = Queue(frame), Queue(), Queue(sample)
        queues = iter((frames, statuses, temperatures))
        processes = (Process(), Process())
        process_iter = iter(processes)
        ctx = SimpleNamespace(
            Queue=lambda **kw: next(queues), Event=Event, Process=lambda **kw: next(process_iter)
        )
        with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
            root = Path(folder)
            (root / "config.json").write_text(json.dumps(asdict(Settings())), encoding="utf-8")
            (root / "thermal.json").write_text(json.dumps(asdict(cfg)), encoding="utf-8")
            for obj, key, value in (
                (runtime, "check_board", Mock()),
                (runtime, "SerialTransport", Mock(return_value=bus)),
                (runtime, "LaserOutput", Mock(return_value=light)),
                (runtime.mp, "get_context", Mock(return_value=ctx)),
                (runtime.time, "monotonic", clock),
                (runtime.time, "sleep", clock.sleep),
                (
                    runtime,
                    "Gimbal",
                    lambda port, settings: Gimbal(port, settings, clock, clock.sleep),
                ),
            ):
                stack.enter_context(patch.object(obj, key, value))
            if failure:
                with self.assertRaisesRegex(RuntimeError, "injected"):
                    runtime.run(root / "config.json", root / "thermal.json", seconds=5)
            else:
                runtime.run(root / "config.json", root / "thermal.json", seconds=5)
        self.assertTrue(all(channel.closed for channel in (frames, statuses, temperatures)))
        self.assertNotIn(True, light.values)
        self.assertFalse(light.values[-1])
        return bus, statuses.items, processes

    def test_complete_path_publishes_valid_and_closes(self):
        bus, statuses, _ = self.execute()
        self.assertTrue(bus.closed)
        self.assertIn("VALID", [s["reading"]["state"] for s in statuses])
        self.assertEqual(statuses[-1]["reading"]["value"], 35)

    def test_unknown_protocol_never_starts_sensor_or_publishes_temperature(self):
        bus, statuses, processes = self.execute(pending=True)
        self.assertTrue(bus.closed)
        self.assertIsNone(processes[1].pid)
        self.assertTrue(all(s["reading"]["value"] is None for s in statuses))
        self.assertEqual(statuses[-1]["sensor_error"], "VENDOR_PROTOCOL_REQUIRED")

    def test_preview_never_opens_motors(self):
        bus, statuses, _ = self.execute(motion=False, pending=True)
        self.assertFalse(bus.frames)
        self.assertTrue(all(s["gimbal"] == "OFF" for s in statuses))

    def test_ui_failure_disables_both_axes(self):
        bus, _, _ = self.execute(failure=True)
        self.assertTrue(bus.closed)
        self.assertEqual([frame[2] for frame in bus.frames[-2:]], [5, 5])

    def test_sensor_dropout_revokes_valid_temperature(self):
        _, statuses, _ = self.execute(dropout=True)
        self.assertIn("VALID", [s["reading"]["state"] for s in statuses])
        self.assertIsNone(statuses[-1]["reading"]["value"])
        self.assertEqual(statuses[-1]["sensor_error"], "SENSOR_TIMEOUT")

    def test_stuck_process_killed_with_bounded_wait(self):
        process = Mock(pid=123)
        process.is_alive.side_effect = [True, True, False]
        runtime.stop_process(process, Mock())
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertTrue(all(c.kwargs["timeout"] == 1 for c in process.join.call_args_list))

    def test_sensor_failure_published(self):
        channel = Queue()
        stop = Mock()
        stop.is_set.return_value = False
        with patch.object(sensor, "open_sensor", return_value=SimpleNamespace(matrix=lambda: [])):
            sensor.worker(ThermalConfig(), channel, stop)
        self.assertEqual(channel.items[0]["kind"], "sensor_error")
        self.assertIn("EMPTY_THERMAL_MATRIX", channel.items[0]["message"])

    def test_preflight_missing_sdk_and_pending_protocol(self):
        def no_sdk(name):
            raise ImportError("not a board")

        checks = inspect(ThermalConfig(), importer=no_sdk)
        self.assertFalse(next(c["ok"] for c in checks if c["check"] == "vendor_protocol"))
        self.assertFalse(next(c["ok"] for c in checks if c["check"] == "SDK"))


if __name__ == "__main__":
    unittest.main()

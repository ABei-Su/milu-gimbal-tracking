"""Waveshare D55 configuration and MaixPy driver boundary contracts."""

from pathlib import Path
import queue
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from thermo.config import load_config
from thermo import sensor
from thermo.probe import collect
from test_thermal import matrix
from test_device import Clock

ROOT = Path(__file__).resolve().parents[1]


class WaveshareTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(ROOT / "thermal.json")

    def test_selected_d55_profile(self):
        self.assertEqual(self.cfg.sensor_backend, "mlx90640_i2c")
        self.assertTrue(self.cfg.sensor_confirmed)
        self.assertFalse(self.cfg.alignment_confirmed)
        self.assertEqual((self.cfg.ir_hfov, self.cfg.ir_vfov), (55, 35))
        self.assertEqual((self.cfg.i2c_bus, self.cfg.sda_pin, self.cfg.scl_pin), (6, "A0", "A1"))

    def test_official_sdk_constructor_and_pin_mapping(self):
        factory = Mock()
        device = SimpleNamespace(MLX90640Celsius=factory, FPS=SimpleNamespace(FPS_8=8))
        maix = SimpleNamespace(
            ext_dev=SimpleNamespace(
                mlx90640=device, cmap=SimpleNamespace(Cmap=SimpleNamespace(WHITE_HOT=0))
            )
        )
        with (
            patch.dict("sys.modules", {"maix": maix}),
            patch.object(sensor, "check_board"),
            patch.object(sensor, "map_pin") as pins,
        ):
            sensor.open_sensor(self.cfg)
        self.assertEqual(
            [c.args for c in pins.call_args_list], [("A0", "I2C6_SDA"), ("A1", "I2C6_SCL")]
        )
        factory.assert_called_once_with(6, 8, 0, -1, -1, 0.95)

    def test_probe_reports_finite_actual_samples(self):
        channel = Mock()
        channel.get.side_effect = [
            {"kind": "thermal", "captured_at": t, "matrix": matrix(34 + t)} for t in (0.1, 0.2)
        ]
        rows = collect(channel, Mock(), self.cfg, 2, 2, clock=lambda: 0.25)
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[1]["roi_p90_c"], 34.2)

    def test_probe_stuck_sensor_has_deadline(self):
        clock = Clock()

        def read(timeout):
            clock.sleep(timeout)
            raise queue.Empty

        channel = Mock()
        channel.get.side_effect = read
        with self.assertRaisesRegex(TimeoutError, "TIMEOUT"):
            collect(channel, Mock(), self.cfg, 2, 1, clock=clock)
        self.assertLessEqual(clock(), 1.21)

    def test_probe_rejects_error_and_partial_frame(self):
        for message in (
            {"kind": "sensor_error", "message": "bad I2C"},
            {"kind": "thermal", "captured_at": 0.1, "matrix": []},
        ):
            channel = Mock()
            channel.get.return_value = message
            with self.assertRaises((RuntimeError, ValueError)):
                collect(channel, Mock(), self.cfg, 1, 2, clock=lambda: 0.2)

    def test_probe_checks_outside_roi(self):
        data = matrix()
        data[0][0] = float("nan")
        channel = Mock()
        channel.get.return_value = {"kind": "thermal", "captured_at": 0.1, "matrix": data}
        with self.assertRaisesRegex(ValueError, "BAD_FULL_FRAME"):
            collect(channel, Mock(), self.cfg, 1, 2, clock=lambda: 0.2)

    def test_probe_duplicate_rejected(self):
        channel = Mock()
        channel.get.return_value = {"kind": "thermal", "captured_at": 0.1, "matrix": matrix()}
        with self.assertRaisesRegex(ValueError, "REPEATED"):
            collect(channel, Mock(), self.cfg, 2, 2, clock=lambda: 0.2)


if __name__ == "__main__":
    unittest.main()

"""Hardware-boundary contract checks without a connected board."""

import configparser
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from milu.maixcam2 import verify_model, LaserOutput, SerialTransport
from milu.settings import Settings


class AdapterTests(unittest.TestCase):
    def test_model_contract_and_local_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("n.axmodel", "v.axmodel"):
                (root / name).write_bytes(b"test model")
            cfg = configparser.ConfigParser()
            cfg["basic"] = {"type": "axmodel", "model_npu": "n.axmodel", "model_vnpu": "v.axmodel"}
            cfg["extra"] = {"model_type": "yolo11", "labels": "person,bicycle"}

            def write():
                with (root / "m.mud").open("w") as stream:
                    cfg.write(stream)

            write()
            self.assertEqual(verify_model(root / "m.mud"), str(root / "m.mud"))
            cfg["basic"]["model_npu"] = "../outside.axmodel"
            write()
            with self.assertRaises(FileNotFoundError):
                verify_model(root / "m.mud")
            cfg["extra"]["labels"] = "deer"
            write()
            with self.assertRaises(ValueError):
                verify_model(root / "m.mud")

    def test_gpio_off_levels(self):
        for active_high in (True, False):
            levels = []
            gpio = types.SimpleNamespace(
                Mode=types.SimpleNamespace(OUT=1),
                Pull=types.SimpleNamespace(PULL_DOWN=0, PULL_UP=1),
                GPIO=lambda *args: types.SimpleNamespace(value=levels.append),
            )
            module = types.SimpleNamespace(gpio=gpio)
            with (
                patch.dict("sys.modules", {"maix": module}),
                patch("milu.maixcam2.check_board"),
                patch("milu.maixcam2.map_pin") as mapping,
            ):
                laser = LaserOutput(Settings(laser_active_high=active_high))
                with self.assertRaisesRegex(ValueError, "disabled"):
                    laser.set(True)
                laser.set(False)
            off = 0 if active_high else 1
            self.assertEqual(levels, [off, off, off])
            mapping.assert_called_once_with("A4", "GPIOA4")

    def transport(self):
        obj = SerialTransport.__new__(SerialTransport)
        obj.fd, obj.cfg, obj.next_write = 7, Settings(), 0.0
        return obj

    def test_partial_frame_never_retried(self):
        obj = self.transport()
        with (
            patch("milu.maixcam2.select.select", return_value=([], [7], [])),
            patch("milu.maixcam2.os.write", return_value=2) as write,
        ):
            with self.assertRaisesRegex(OSError, "PARTIAL_FRAME"):
                obj.send(b"123456")
            write.assert_called_once_with(7, b"123456")

    def test_tx_timeout_no_write(self):
        with (
            patch("milu.maixcam2.select.select", return_value=([], [], [])),
            patch("milu.maixcam2.os.write") as write,
        ):
            with self.assertRaises(TimeoutError):
                self.transport().send(b"123456")
            write.assert_not_called()

    def test_interframe_idle_and_wire_duration(self):
        obj = self.transport()
        obj.next_write = 10.01
        with (
            patch("milu.maixcam2.time.monotonic", return_value=10.0),
            patch("milu.maixcam2.time.sleep") as sleep,
            patch("milu.maixcam2.select.select", return_value=([], [7], [])),
            patch("milu.maixcam2.os.write", return_value=6),
        ):
            obj.send(b"123456")
        self.assertAlmostEqual(sleep.call_args.args[0], 0.01)
        self.assertAlmostEqual(obj.next_write, 10 + 60 / 115200 + 0.002)

    def test_read_is_bounded_nonblocking(self):
        with (
            patch("milu.maixcam2.select.select", return_value=([7], [], [])),
            patch("milu.maixcam2.os.read", return_value=b"data") as read,
        ):
            self.assertEqual(self.transport().read(), b"data")
            read.assert_called_once_with(7, 256)

    def test_close_idempotent(self):
        obj = self.transport()
        with patch("milu.maixcam2.os.close") as close:
            obj.close()
            obj.close()
        close.assert_called_once_with(7)


if __name__ == "__main__":
    unittest.main()

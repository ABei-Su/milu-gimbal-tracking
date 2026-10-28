"""Offline thermal state, touch and display contracts."""

from dataclasses import asdict, replace
from types import SimpleNamespace
import unittest
from milu.settings import Settings
from milu.targeting import Aim
from milu.tracking import Detection
from thermo.config import ThermalConfig
from thermo.temperature import TemperatureGate, roi_stats, roi_covered
from thermo.selection import Selection, TrackState
from thermo.ui import display_reading
from thermo.runtime import measurement_reason
from thermo.sensor import open_sensor


def matrix(value=35.0):
    return [[value for _ in range(32)] for _ in range(24)]


def target(at=1, box=(160, 120, 480, 360)):
    return Detection(*box, 640, 480, 0.9, at)


def ready_gate():
    gate = TemperatureGate(ThermalConfig(stabilization=0.1))
    gate.update(0, session=1, eligible=True, reason="")
    for t in (0.2, 0.3, 0.4, 0.5, 0.6):
        gate.update(
            t, session=1, eligible=True, reason="", frame={"captured_at": t, "matrix": matrix()}
        )
    return gate


class ThermalTests(unittest.TestCase):
    def test_stats_reject_hot_bad_pixel(self):
        data = matrix()
        data[12][16] = 200
        self.assertEqual(roi_stats(data, ThermalConfig()), (35, 35, 35))

    def test_stats_invalid_shape_type_and_missing_pixels(self):
        for data in ([], [[35] * 31] * 24, [[True] * 32] * 24, matrix(float("nan"))):
            with self.subTest(data=str(data)[:20]), self.assertRaises(ValueError):
                roi_stats(data, ThermalConfig())

    def test_range_and_offset(self):
        self.assertEqual(roi_stats(matrix(), ThermalConfig(temperature_offset=1)), (36, 36, 36))
        with self.assertRaises(ValueError):
            roi_stats(matrix(400), ThermalConfig())

    def test_valid_then_loss_immediately_clears(self):
        gate = ready_gate()
        self.assertEqual(gate.reading.value, 35)
        reading = gate.update(0.7, session=1, eligible=False, reason="LOST")
        self.assertEqual(reading.state, "INVALID")
        self.assertIsNone(reading.value)
        self.assertFalse(gate.history)

    def test_new_selection_starts_new_window(self):
        gate = ready_gate()
        reading = gate.update(0.7, session=2, eligible=True, reason="")
        self.assertEqual(reading.state, "STABILIZING")
        self.assertFalse(gate.history)

    def test_duplicate_not_counted_and_timeout_invalid(self):
        gate = ready_gate()
        last = {"captured_at": 0.6, "matrix": matrix(100)}
        reading = gate.update(0.7, session=1, eligible=True, reason="", frame=last)
        self.assertEqual(reading.value, 35)
        self.assertEqual(len(gate.history), 5)
        self.assertIsNone(gate.update(1.3, session=1, eligible=True, reason="").value)

    def test_out_of_order_and_future_frame(self):
        for timestamp in (0.55, 2):
            gate = ready_gate()
            reading = gate.update(
                0.7,
                session=1,
                eligible=True,
                reason="",
                frame={"captured_at": timestamp, "matrix": matrix()},
            )
            self.assertEqual(reading.state, "INVALID")

    def test_bad_frame_fails_closed(self):
        for frame in ({}, {"captured_at": "bad"}, {"captured_at": 0.7, "matrix": []}):
            gate = ready_gate()
            reading = gate.update(0.7, session=1, eligible=True, reason="", frame=frame)
            self.assertEqual(reading.state, "INVALID")

    def test_unstable_window_not_published(self):
        gate = ready_gate()
        result = gate.update(
            0.7,
            session=1,
            eligible=True,
            reason="",
            frame={"captured_at": 0.7, "matrix": matrix(40)},
        )
        self.assertEqual(result.reason, "TEMPERATURE_UNSTABLE")
        self.assertIsNone(result.value)

    def test_clock_reversal_clears(self):
        gate = ready_gate()
        with self.assertRaises(ValueError):
            gate.update(0.5, session=1, eligible=True, reason="")
        self.assertFalse(gate.history)

    def test_pre_stability_frames_not_used(self):
        gate = TemperatureGate(ThermalConfig(stabilization=0.1))
        gate.update(0, session=1, eligible=True, reason="")
        reading = gate.update(
            0.2,
            session=1,
            eligible=True,
            reason="",
            frame={"captured_at": 0.05, "matrix": matrix()},
        )
        self.assertEqual(reading.samples, 0)

    def test_geometry_rejects_small_and_off_center(self):
        cfg = ThermalConfig()
        self.assertTrue(roi_covered(target(), Settings(), cfg))
        self.assertFalse(roi_covered(target(box=(310, 230, 330, 250)), Settings(), cfg))
        self.assertFalse(roi_covered(target(box=(0, 0, 200, 200)), Settings(), cfg))

    def test_config_validation(self):
        for changes in (
            {"roi_size": 4},
            {"fusion_frames": 4},
            {"sensor_backend": "guessed_uart"},
            {"sensor_timeout": 0.01},
            {"ir_hfov": float("nan")},
            {"roi_cx": 0},
            {"sensor_confirmed": 1},
            {"sensor_fps": 8.0},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ThermalConfig(**changes)
        with self.assertRaises(ValueError):
            ThermalConfig(sda_pin="A21").check_pins(Settings())

    def test_pending_protocol_cannot_open(self):
        with self.assertRaisesRegex(ValueError, "PROTOCOL"):
            open_sensor(ThermalConfig(sensor_confirmed=True))
        with self.assertRaisesRegex(ValueError, "CONFIRM"):
            open_sensor(ThermalConfig(sensor_backend="mlx90640_i2c"))

    def test_measurement_guards(self):
        cfg = ThermalConfig(alignment_confirmed=True)
        args = dict(
            base=Settings(),
            cfg=cfg,
            target=target(),
            aim=Aim(0, 0, True, False),
            measured=(0, 0),
            previous_goal=(0, 0),
            speed=0,
            now=1,
            motion=True,
            sensor_ready=True,
        )
        self.assertEqual(measurement_reason(**args), "")
        for key, value, reason in (
            ("motion", False, "ENABLE_TRACK"),
            ("target", None, "SELECT_OR_RESELECT_EYE"),
            ("now", 2, "STALE_VISION"),
            ("cfg", replace(cfg, alignment_confirmed=False), "ALIGN_RGB_IR_FIRST"),
            ("speed", 1, "GIMBAL_MOVING"),
            ("sensor_ready", False, "SENSOR_NOT_READY"),
            ("aim", Aim(0, 0, False, False), "CENTER_AND_HOLD"),
        ):
            self.assertEqual(measurement_reason(**dict(args, **{key: value})), reason)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = ThermalConfig()
        self.selection = Selection(640, 480, self.cfg)

    def select(self):
        self.selection.touch(160, 120, True)
        return self.selection.touch(480, 360, False)

    def test_select_track_lose_requires_reselection(self):
        self.assertEqual(self.select()[0], "init")
        result = SimpleNamespace(x=160, y=120, w=320, h=240, score=0.9)
        self.assertIsNotNone(self.selection.accept(result, 1))
        result.score = 0.1
        self.assertIsNone(self.selection.accept(result, 2))
        result.score = 0.9
        self.assertIsNone(self.selection.accept(result, 3))
        self.assertEqual(self.selection.state, TrackState.LOST)
        self.select()
        self.assertIsNotNone(self.selection.accept(result, 4))
        self.assertEqual(self.selection.session, 2)

    def test_abrupt_identity_change_rejected(self):
        self.select()
        result = SimpleNamespace(x=300, y=250, w=80, h=80, score=0.99)
        self.assertIsNone(self.selection.accept(result, 1))

    def test_click_not_drag_and_button_release(self):
        self.selection.touch(200, 200, True)
        self.selection.touch(201, 201, False)
        self.assertEqual(self.selection.state, TrackState.SELECTING)
        self.selection.touch(150, 460, True)
        self.selection.touch(500, 460, False)
        self.assertFalse(self.selection.motion)
        self.selection.touch(150, 460, True)
        self.selection.touch(150, 460, False)
        self.assertTrue(self.selection.motion)

    def test_drag_clips_hud(self):
        self.selection.touch(300, 200, True)
        self.selection.touch(200, 0, False)
        self.assertGreaterEqual(self.selection.box[1], 96)

    def test_display_never_shows_stale_or_wrong_session(self):
        self.select()
        self.selection.motion = True
        status = {"at": 1, "session": 1, "reading": asdict(ready_gate().reading)}
        status["reading"]["acquired_at"] = 1
        self.assertEqual(
            display_reading(status, self.selection, target(), 1, Settings(), self.cfg)["value"], 35
        )
        for now, session in ((2, 1), (1, 2)):
            status["session"] = session
            self.assertIsNone(
                display_reading(status, self.selection, target(), now, Settings(), self.cfg)[
                    "value"
                ]
            )

    def test_track_off_immediately_invalidates_screen(self):
        self.select()
        status = {"at": 1, "session": 1, "reading": asdict(ready_gate().reading)}
        status["reading"]["acquired_at"] = 1
        self.assertIsNone(
            display_reading(status, self.selection, target(), 1, Settings(), self.cfg)["value"]
        )


if __name__ == "__main__":
    unittest.main()

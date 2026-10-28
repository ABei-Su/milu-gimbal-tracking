import unittest
from dataclasses import replace
from milu.settings import Settings
from milu.targeting import VisualServo
from test_device import target


class PredictionTests(unittest.TestCase):
    def test_bounded_prediction_and_repeated_frame(self):
        s = VisualServo(replace(Settings(), prediction_horizon=0.06))
        s.update(target(1, cx=350), 1, (0, 0), 1)
        s.update(target(1.06, cx=400), 1.06, (0, 0), 1)
        predicted = s.predicted_error(1.12)
        self.assertGreater(predicted[0], s.filtered[0])
        self.assertLessEqual(predicted[0] - s.filtered[0], 0.025 + 1e-9)
        self.assertEqual(predicted, s.predicted_error(2))
        v = s.image_velocity
        s.update(target(1.06, cx=400), 1.13, (0, 0), 1)
        self.assertEqual(s.image_velocity, v)
        s.update(None, 1.14, (0, 0), 1)
        self.assertEqual(s.image_velocity, (0.0, 0.0))

    def test_default_has_no_prediction_and_invalid_horizon_rejected(self):
        s = VisualServo(Settings())
        s.update(target(1, cx=350), 1, (0, 0), 1)
        s.update(target(1.06, cx=400), 1.06, (0, 0), 1)
        self.assertEqual(s.predicted_error(1.12), s.filtered)
        for value in (-1, 0.2, float("nan")):
            with self.assertRaises(ValueError):
                replace(Settings(), prediction_horizon=value)

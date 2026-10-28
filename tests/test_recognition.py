"""Low-score continuity never acquires new targets or authorizes the laser."""

import unittest
from milu.settings import Settings
from milu.targeting import TargetSelector, TargetStream, Aim
from milu.runtime import light_eligible
from test_device import target


class RecognitionTests(unittest.TestCase):
    def test_fresh_weak_overlap_continues(self):
        selector = TargetSelector(Settings())
        selector.select([target(0)], 0, 0)
        selected, ambiguous = selector.select([target(0.1, 322, score=0.45)], 0.1, 0.1)
        self.assertIsNotNone(selected)
        self.assertTrue(ambiguous)
        self.assertEqual(selector.generation, 1)

    def test_held_weak_frame_does_not_extend_strong_evidence_deadline(self):
        stream = TargetStream(Settings())
        stream.update({"detections": [target(0)], "captured_at": 0}, 0)
        stream.update({"detections": [target(0.1, score=0.45)], "captured_at": 0.1}, 0.1)
        self.assertIsNone(stream.update(None, 0.3)[0])

    def test_weak_never_acquires(self):
        self.assertIsNone(TargetSelector(Settings()).select([target(0, score=0.45)], 0, 0)[0])

    def test_weak_lifetime_requires_strong_refresh(self):
        selector = TargetSelector(Settings())
        selector.select([target(0)], 0, 0)
        self.assertIsNotNone(selector.select([target(0.1, score=0.45)], 0.1, 0.1)[0])
        self.assertIsNotNone(selector.select([target(0.2, score=0.45)], 0.2, 0.2)[0])
        self.assertIsNone(selector.select([target(0.3, score=0.45)], 0.3, 0.3)[0])
        self.assertIsNotNone(selector.select([target(0.4)], 0.4, 0.4)[0])

    def test_weak_wrong_location_and_multiple_rejected(self):
        for candidates in (
            [target(0.1, 500, score=0.45)],
            [target(0.1, 320, score=0.45), target(0.1, 322, score=0.45)],
        ):
            selector = TargetSelector(Settings())
            selector.select([target(0)], 0, 0)
            self.assertIsNone(selector.select(candidates, 0.1, 0.1)[0])

    def test_light_checks_score_even_without_ambiguity(self):
        self.assertFalse(
            light_eligible(
                Settings(),
                target(0.1, score=0.45),
                Aim(0, 0, True, False),
                False,
                (0, 0),
                (0, 0),
                0.1,
            )
        )

    def test_setting_validation_and_disable(self):
        with self.assertRaises(ValueError):
            Settings(track_confidence=0)
        selector = TargetSelector(Settings(track_confidence=0.65))
        selector.select([target(0)], 0, 0)
        self.assertIsNone(selector.select([target(0.1, score=0.45)], 0.1, 0.1)[0])

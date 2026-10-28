"""Cached evaluation threshold contracts without loading an ML runtime."""

import unittest
from tools.evaluate_detector import score_rows, iou


class EvaluationTests(unittest.TestCase):
    def test_matching_and_threshold(self):
        box = [0.5, 0.5, 0.2, 0.2]
        rows = [{"expected": [box], "predictions": [(0.6, box), (0.4, box)]}]
        self.assertEqual(score_rows(rows, "val", 0.65)["fn"], 1)
        result = score_rows(rows, "val", 0.55)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 0, 0))
        self.assertEqual(score_rows(rows, "val", 0.25)["fp"], 1)

    def test_empty_negative_and_cache_floor(self):
        self.assertEqual(score_rows([{"expected": [], "predictions": []}], "val", 0.25)["f1"], 0)
        with self.assertRaises(ValueError):
            score_rows([], "val", 0.1)
        self.assertEqual(iou([0.2, 0.2, 0.1, 0.1], [0.8, 0.8, 0.1, 0.1]), 0)

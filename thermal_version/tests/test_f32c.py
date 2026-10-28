import unittest
from functools import reduce
from operator import xor

from milu import f32c


def feedback_frame(motor, kind, value):
    body = bytes((0x7A, motor, kind)) + value.to_bytes(4, "big", signed=True)
    return body + bytes((reduce(xor, body), 0x7B))


class ProtocolTests(unittest.TestCase):
    def test_manual_golden_commands(self):
        vectors = [
            (f32c.enable(1), "7a 01 06 7d 7b"),
            (f32c.enable(2), "7a 02 06 7e 7b"),
            (f32c.disable(2), "7a 02 05 7d 7b"),
            (f32c.mode(2), "7a 02 00 00 01 79 7b"),
            (f32c.mode(2, 3), "7a 02 00 00 03 7b 7b"),
            (f32c.speed(2, 100), "7a 02 01 00 64 1d 7b"),
            (f32c.speed(2, -100), "7a 02 01 ff 9c 1a 7b"),
            (f32c.position(2, 3600), "7a 02 02 00 00 0e 10 64 7b"),
            (f32c.position(2, -3600), "7a 02 02 ff ff f1 f0 7b 7b"),
            (f32c.position(1, 0), "7a 01 02 00 00 00 00 79 7b"),
            (f32c.query(2, 1), "7a 02 0e 01 77 7b"),
        ]
        for actual, expected in vectors:
            with self.subTest(expected=expected):
                self.assertEqual(actual, bytes.fromhex(expected))

    def test_invalid_commands(self):
        cases = [
            (f32c.enable, (0,)),
            (f32c.enable, (True,)),
            (f32c.mode, (1, 5)),
            (f32c.speed, (1, 1001)),
            (f32c.speed, (1, 1.5)),
            (f32c.position, (1, 18773853)),
            (f32c.position, (1, -18773853)),
            (f32c.query, (1, 5)),
        ]
        for fn, args in cases:
            with self.subTest(fn=fn, args=args), self.assertRaises(ValueError):
                fn(*args)

    def test_manual_feedback(self):
        parser = f32c.FeedbackParser()
        frames = "7a 02 01 00 00 0e 10 67 7b 7a 02 04 00 00 04 b0 c8 7b"
        items = parser.feed(bytes.fromhex(frames))
        self.assertEqual([(v.value, v.unit) for v in items], [(360, "deg"), (12, "V")])

    def test_every_fragment_boundary(self):
        frame = feedback_frame(1, 1, -3600)
        for split in range(10):
            parser = f32c.FeedbackParser()
            items = parser.feed(frame[:split]) + parser.feed(frame[split:])
            self.assertEqual([v.value for v in items], [-360])

    def test_noise_corruption_and_concatenation(self):
        good = feedback_frame(2, 0, -100)
        bad = bytearray(good)
        bad[7] ^= 1
        parser = f32c.FeedbackParser()
        items = parser.feed(b"noise\x7a" + bytes(bad) + good + good)
        self.assertEqual([v.raw for v in items], [-100, -100])

    def test_payload_delimiters_are_not_boundaries(self):
        raw = 0x007A7B7A
        result = f32c.FeedbackParser().feed(feedback_frame(2, 1, raw))
        self.assertEqual(result[0].raw, raw)

    def test_unsupported_feedback_is_discarded(self):
        parser = f32c.FeedbackParser()
        result = parser.feed(feedback_frame(3, 0, 1) + feedback_frame(1, 9, 1))
        self.assertEqual(result, [])

    def test_bounded_residual_and_timeout_reset(self):
        parser = f32c.FeedbackParser()
        parser.feed(b"\x7a" * 10000)
        self.assertLessEqual(len(parser._pending), 8)
        parser.reset()
        self.assertEqual(parser.feed(feedback_frame(1, 0, 100))[0].value, 100)

    def test_bytes_only(self):
        with self.assertRaises(ValueError):
            f32c.FeedbackParser().feed("not bytes")

import unittest
from milu.diagnostics import probe
from test_device import Clock
from functools import reduce
from operator import xor


class Port:
    def __init__(self, response=b""):
        self.response = response
        self.pending = b""
        self.sent = []

    def clear_input(self):
        self.pending = b""

    def send(self, frame):
        self.sent.append(frame)
        self.pending = self.response

    def read(self):
        data, self.pending = self.pending, b""
        return data


class DiagnosticTests(unittest.TestCase):
    def test_no_data_bounded_and_only_query_commands(self):
        clock, port = Clock(), Port()
        result = probe(port, 1, clock=clock, sleep=clock.sleep)
        self.assertEqual(result["status"], "NO_BYTES")
        self.assertLessEqual(clock(), 0.51)
        self.assertEqual(port.sent, [bytes.fromhex("7a010e01747b")])

    def test_valid_position(self):
        body = bytes.fromhex("7a020100000e10")
        port = Port(body + bytes([reduce(xor, body), 0x7B]))
        clock = Clock()
        result = probe(port, 2, clock=clock, sleep=clock.sleep)
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["position_deg"], 360)

    def test_garbage_not_reported_as_no_bytes(self):
        clock = Clock()
        result = probe(Port(b"bad"), 1, clock=clock, sleep=clock.sleep)
        self.assertEqual(result["status"], "UNMATCHED_BYTES")
        self.assertEqual(result["rx_hex"], "62 61 64")

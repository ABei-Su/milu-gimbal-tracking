"""Verified subset of the supplied F32C July 2026 protocol; no I/O."""

from dataclasses import dataclass
from functools import reduce
from operator import xor


def _integer(value: int, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"expected integer in [{low}, {high}]")
    return value


def _frame(motor: int, command: int, payload: bytes = b"") -> bytes:
    _integer(motor, 1, 2)
    body = bytes((0x7A, motor, command)) + payload
    return body + bytes((reduce(xor, body), 0x7B))


def enable(motor: int) -> bytes:
    return _frame(motor, 0x06)


def disable(motor: int) -> bytes:
    return _frame(motor, 0x05)


def mode(motor: int, value: int = 1) -> bytes:
    """0 speed; 1/2 multi/single T profile; 3/4 multi/single direct."""
    return _frame(motor, 0x00, _integer(value, 0, 4).to_bytes(2, "big"))


def speed(motor: int, rpm: int) -> bytes:
    """Signed RPM in speed mode; positive magnitude in position mode."""
    value = _integer(rpm, -1000, 1000)
    return _frame(motor, 0x01, value.to_bytes(2, "big", signed=True))


def position(motor: int, deci_degrees: int) -> bytes:
    """Absolute multi-turn angle in 0.1 degrees, bounded by manual p7."""
    value = _integer(deci_degrees, -18773852, 18773852)
    return _frame(motor, 0x02, value.to_bytes(4, "big", signed=True))


def query(motor: int, kind: int) -> bytes:
    return _frame(motor, 0x0E, bytes((_integer(kind, 0, 4),)))


@dataclass(frozen=True)
class Feedback:
    motor: int
    kind: int
    raw: int

    @property
    def value(self) -> float:
        return self.raw / (10 if self.kind in (1, 2) else 100 if self.kind == 4 else 1)

    @property
    def unit(self) -> str:
        return ("rpm", "deg", "deg", "rev/s^2", "V")[self.kind]


class FeedbackParser:
    """Fixed-length framing supports fragmented reads and embedded delimiters.

    Residual storage is at most eight bytes. Callers must expire incomplete
    responses on transaction timeout and match motor/type to their query.
    """

    def __init__(self) -> None:
        self._pending = bytearray()

    def reset(self) -> None:
        self._pending.clear()

    def feed(self, data: bytes) -> list[Feedback]:
        if not isinstance(data, bytes):
            raise ValueError("feed expects bytes")
        results = []
        for byte in data:
            self._pending.append(byte)
            while self._pending and self._pending[0] != 0x7A:
                del self._pending[0]
            if len(self._pending) < 9:
                continue
            p = self._pending
            valid = p[1] in (1, 2) and p[2] <= 4 and p[8] == 0x7B and reduce(xor, p[:7]) == p[7]
            if valid:
                results.append(Feedback(p[1], p[2], int.from_bytes(p[3:7], "big", signed=True)))
                p.clear()
            else:
                del p[0]
        return results

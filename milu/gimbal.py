"""Single-owner F32C session with feedback-origin capture and bounded I/O."""

import math
import time
from enum import Enum
from milu import f32c


class GimbalState(str, Enum):
    NEW = "new"
    STARTING = "starting"
    READY = "ready"
    FAULT = "fault"
    CLOSED = "closed"


class Gimbal:
    def __init__(self, transport, cfg, clock=time.monotonic, sleep=time.sleep):
        self.transport, self.cfg, self.clock, self.sleep = transport, cfg, clock, sleep
        self._state = GimbalState.NEW
        self.zero = (0.0, 0.0)
        self.measured = (0.0, 0.0)
        self.last_feedback = None
        self.errors = []
        self.parser = f32c.FeedbackParser()

    @property
    def state(self):
        return self._state

    def query_position(self, motor):
        self.parser.reset()
        self.transport.clear_input()
        self.transport.send(f32c.query(motor, 1))
        deadline = self.clock() + self.cfg.query_timeout
        while self.clock() < deadline:
            for item in self.parser.feed(self.transport.read()):
                if item.motor == motor and item.kind == 1:
                    return item.value
            self.sleep(0.001)
        raise TimeoutError(f"NO_FEEDBACK: motor {motor}")

    def start(self):
        if self.state != GimbalState.NEW:
            raise RuntimeError("start only valid for NEW session")
        self._state = GimbalState.STARTING
        try:
            self.sleep(self.cfg.boot_wait)
            for motor in (1, 2):
                self.transport.send(f32c.disable(motor))
            initial = tuple(self.query_position(motor) for motor in (1, 2))
            # Preload the current target; then follow vendor enable/mode/speed sequence.
            for motor, angle in zip((1, 2), initial):
                self.transport.send(f32c.speed(motor, 0))
                self.transport.send(f32c.position(motor, round(angle * 10)))
                self.transport.send(f32c.enable(motor))
                self.transport.send(f32c.mode(motor, 3))
                self.transport.send(f32c.speed(motor, self.cfg.position_rpm))
                self.transport.send(f32c.position(motor, round(angle * 10)))
            self.zero = tuple(self.query_position(motor) for motor in (1, 2))
            self.measured = (0.0, 0.0)
            self.last_feedback = self.clock()
            self._state = GimbalState.READY
            self.move(0, 0)
        except Exception as exc:
            self._fault(exc)
            raise

    def poll(self):
        if self.state != GimbalState.READY:
            raise RuntimeError("NOT_READY")
        try:
            raw = tuple(self.query_position(motor) for motor in (1, 2))
            measured = tuple(value - zero for value, zero in zip(raw, self.zero))
            for value, limit in zip(measured, (self.cfg.yaw_limit, self.cfg.pitch_limit)):
                if not math.isfinite(value) or abs(value) > limit + self.cfg.reached_tolerance:
                    raise ValueError("FEEDBACK_OUTSIDE_LIMIT")
            self.measured = measured
            self.last_feedback = self.clock()
            return self.measured
        except Exception as exc:
            self._fault(exc)
            raise

    def move(self, yaw, pitch):
        if self.state != GimbalState.READY:
            raise RuntimeError("NOT_READY")
        try:
            if (
                self.last_feedback is None
                or self.clock() - self.last_feedback > self.cfg.feedback_timeout
            ):
                raise TimeoutError("STALE_FEEDBACK")
            frames = []
            for motor, value, zero, limit in zip(
                (1, 2),
                (yaw, pitch),
                self.zero,
                (self.cfg.yaw_limit, self.cfg.pitch_limit),
            ):
                if not math.isfinite(value) or abs(value) > limit:
                    raise ValueError("TARGET_OUTSIDE_LIMIT")
                # Clamp quantization inward at non-decimal configured limits.
                raw = round((zero + value) * 10)
                raw = max(
                    math.ceil((zero - limit) * 10),
                    min(math.floor((zero + limit) * 10), raw),
                )
                frames.append(f32c.position(motor, raw))
            for frame in frames:
                self.transport.send(frame)
        except Exception as exc:
            self._fault(exc)
            raise

    def _disable(self):
        for motor in (1, 2):
            try:
                self.transport.send(f32c.disable(motor))
            except Exception as exc:
                self.errors.append(f"DISABLE_FAILED motor={motor}: {exc}")

    def _fault(self, exc):
        self._state = GimbalState.FAULT
        self.errors.append(str(exc))
        self._disable()

    def close(self):
        if self.state == GimbalState.CLOSED:
            return
        self._disable()
        try:
            self.transport.close()
        finally:
            self._state = GimbalState.CLOSED

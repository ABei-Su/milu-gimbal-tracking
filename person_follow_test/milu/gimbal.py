"""Single-owner F32C session with feedback-origin capture and bounded I/O."""

import math
import time
from enum import Enum
from milu import f32c
from milu.homing import home_targets, approach


class GimbalState(str, Enum):
    NEW = "new"
    STARTING = "starting"
    HOMING = "homing"
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

    def query_position(self, motor, kind=1):
        self.parser.reset()
        self.transport.clear_input()
        self.transport.send(f32c.query(motor, kind))
        deadline = self.clock() + self.cfg.query_timeout
        while self.clock() < deadline:
            for item in self.parser.feed(self.transport.read()):
                if item.motor == motor and item.kind == kind:
                    return item.value
            self.sleep(0.001)
        raise TimeoutError(f"NO_FEEDBACK: motor {motor}")

    def start(self, cancelled=lambda: False, acquired=lambda: False):
        if self.state != GimbalState.NEW:
            raise RuntimeError("start only valid for NEW session")
        self._state = GimbalState.STARTING
        try:
            self.sleep(self.cfg.boot_wait)
            if cancelled():
                raise InterruptedError("HOME_CANCELLED")
            initial = tuple(self.query_position(motor) for motor in (1, 2))
            home = None
            if self.cfg.home_enabled:
                mechanical = tuple(self.query_position(m, 2) for m in (1, 2))
                print(f"[HOME] total={initial} mechanical={mechanical}", flush=True)
                home = home_targets(initial, mechanical, self.cfg.home_max_travel)
            elif self.cfg.startup_pitch_lift:
                home = (initial[0], initial[1] - self.cfg.startup_pitch_lift)
                print(
                    f"[LIFT] relative up={self.cfg.startup_pitch_lift} deg; "
                    "motor 1 holds; NOT calibrated horizontal zero",
                    flush=True,
                )
            # Preload the current target; then follow vendor enable/mode/speed sequence.
            for motor, angle in zip((1, 2), initial):
                self.transport.send(f32c.speed(motor, 0))
                self.transport.send(f32c.position(motor, round(angle * 10)))
                self.transport.send(f32c.enable(motor))
                self.transport.send(f32c.mode(motor, 3))
                self.transport.send(f32c.speed(motor, self.cfg.position_rpm))
                self.transport.send(f32c.position(motor, round(angle * 10)))
            if home is not None:
                self._state = GimbalState.HOMING
                self.zero = self._home(initial, home, cancelled, acquired)
            else:
                self.zero = tuple(self.query_position(motor) for motor in (1, 2))
            self.measured = (0.0, 0.0)
            self.last_feedback = self.clock()
            self._state = GimbalState.READY
            self.move(0, 0)
        except Exception as exc:
            self._fault(exc)
            raise

    def _home(self, initial, goal, cancelled, acquired=lambda: False):
        reference = initial
        started = previous = self.clock()
        stable = 0
        print(f"[HOME] start={initial} target={goal} rate={self.cfg.home_rate}", flush=True)
        while self.clock() - started < self.cfg.home_timeout:
            if cancelled():
                raise InterruptedError("HOME_CANCELLED")
            measured = tuple(self.query_position(m) for m in (1, 2))
            for motor, (target, actual) in enumerate(zip(reference, measured), 1):
                error = target - actual
                if abs(error) > self.cfg.home_error:
                    raise ValueError(
                        f"HOME_FOLLOWING_ERROR: motor={motor} reference={target:.2f} "
                        f"measured={actual:.2f} error={error:.2f} "
                        f"limit={self.cfg.home_error} goal={goal[motor - 1]:.2f}"
                    )
            if self.cfg.startup_pitch_lift and acquired():
                for motor, angle in zip((1, 2), measured):
                    self.transport.send(f32c.position(motor, round(angle * 10)))
                print(f"[SEARCH] FACE_ACQUIRED: lift stopped at {measured}", flush=True)
                return measured
            now = self.clock()
            step = self.cfg.home_rate * min(max(now - previous, 0), 0.1)
            previous = now
            reference = approach(reference, goal, step)
            for m, angle in zip((1, 2), reference):
                self.transport.send(f32c.position(m, round(angle * 10)))
            near = reference == goal and all(abs(a - b) <= 0.3 for a, b in zip(measured, goal))
            stable = stable + 1 if near else 0
            if stable >= 5:
                print(
                    "[LIFT] READY: relative lift reached; tracking origin captured"
                    if self.cfg.startup_pitch_lift
                    else "[HOME] READY: calibrated mechanical zero reached",
                    flush=True,
                )
                return goal
            self.sleep(0.05)
        raise TimeoutError("HOME_TIMEOUT")

    def poll(self):
        if self.state != GimbalState.READY:
            raise RuntimeError("NOT_READY")
        try:
            raw = tuple(self.query_position(motor) for motor in (1, 2))
            measured = tuple(value - zero for value, zero in zip(raw, self.zero))
            for value, limit in zip(measured, self.cfg.motion_limits):
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
                self.cfg.motion_limits,
            ):
                if not math.isfinite(value) or abs(value) > limit:
                    raise ValueError("TARGET_OUTSIDE_LIMIT")
                # Clamp quantization inward at non-decimal configured limits.
                raw = round((zero + value) * 10)
                if math.isfinite(limit):
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

"""Deterministic single-target reference controller with no hardware effects."""

import math
from dataclasses import dataclass
from enum import Enum


def _finite(*values: float) -> bool:
    return all(type(v) in (int, float) and math.isfinite(v) for v in values)


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class Detection:
    """Selected target in original image pixels, time in monotonic seconds."""

    x1: float
    y1: float
    x2: float
    y2: float
    width: int
    height: int
    confidence: float
    captured_at: float

    def validate(self) -> None:
        if not _finite(self.x1, self.y1, self.x2, self.y2, self.confidence, self.captured_at):
            raise ValueError("non-finite detection")
        if type(self.width) is not int or type(self.height) is not int:
            raise ValueError("image dimensions must be integers")
        if not (0 <= self.x1 < self.x2 <= self.width and 0 <= self.y1 < self.y2 <= self.height):
            raise ValueError("box outside original image or empty")
        if not 0 <= self.confidence <= 1 or self.captured_at < 0:
            raise ValueError("invalid confidence or capture time")


@dataclass(frozen=True)
class Config:
    """Simulation defaults only; directions/limits/gain need physical calibration."""

    yaw_min: float = -20.0
    yaw_max: float = 20.0
    pitch_min: float = -10.0
    pitch_max: float = 10.0
    yaw_sign: int = 1
    pitch_sign: int = 1
    gain: float = 20.0  # degrees/second per normalized half-image error
    max_rate: float = 8.0  # degrees/second
    deadband: float = 0.03
    min_confidence: float = 0.6
    stale_after: float = 0.25
    lost_after: float = 0.5
    dwell: float = 0.3
    max_dt: float = 0.05  # cap step after delayed update

    def __post_init__(self) -> None:
        values = tuple(getattr(self, key) for key in self.__dataclass_fields__)
        if not _finite(*values):
            raise ValueError("non-finite configuration")
        if not (-1877385.2 <= self.yaw_min < self.yaw_max <= 1877385.2):
            raise ValueError("invalid yaw limits")
        if not (-1877385.2 <= self.pitch_min < self.pitch_max <= 1877385.2):
            raise ValueError("invalid pitch limits")
        if self.yaw_sign not in (-1, 1) or self.pitch_sign not in (-1, 1):
            raise ValueError("axis signs must be -1 or 1")
        if not (0 <= self.deadband < 1 and 0 <= self.min_confidence <= 1):
            raise ValueError("invalid confidence/deadband")
        if (
            min(
                self.gain,
                self.max_rate,
                self.stale_after,
                self.lost_after,
                self.dwell,
                self.max_dt,
            )
            <= 0
        ):
            raise ValueError("time/rate parameters must be positive")
        if self.stale_after > self.lost_after:
            raise ValueError("stale timeout exceeds lost timeout")


class State(str, Enum):
    IDLE = "idle"
    TRACKING = "tracking"
    CENTERED = "centered"
    LOST = "lost"
    STOPPED = "stopped"
    FAULT = "fault"


@dataclass(frozen=True)
class Command:
    yaw_deg: float
    pitch_deg: float
    state: State
    reason: str
    light_on: bool = False


class Tracker:
    def __init__(self, config: Config = Config(), yaw: float = 0, pitch: float = 0) -> None:
        if not _finite(yaw, pitch):
            raise ValueError("non-finite initial position")
        if not (
            config.yaw_min <= yaw <= config.yaw_max
            and config.pitch_min <= pitch <= config.pitch_max
        ):
            raise ValueError("initial position outside limits")
        self.config = config
        self._yaw, self._pitch = yaw, pitch
        self._state = State.IDLE
        self._last_tick = None
        self._last_capture = None
        self._center_since = None

    @property
    def state(self) -> State:
        return self._state

    def _result(self, reason: str) -> Command:
        return Command(self._yaw, self._pitch, self._state, reason)

    def _transition(self, state: State) -> None:
        self._state = state

    def stop(self) -> Command:
        if self.state not in (State.STOPPED, State.FAULT):
            self._transition(State.STOPPED)
        return self._result("STOP_REQUEST")

    def fail(self) -> Command:
        if self.state not in (State.STOPPED, State.FAULT):
            self._transition(State.FAULT)
        return self._result("EXTERNAL_FAULT")

    def update(self, target: Detection | None, now: float) -> Command:
        if self.state in (State.STOPPED, State.FAULT):
            raise RuntimeError("TERMINAL_STATE: construct a new calibrated session")
        try:
            if (
                not _finite(now)
                or now < 0
                or (self._last_tick is not None and now <= self._last_tick)
            ):
                raise ValueError("clock must be finite, nonnegative and strictly increasing")
            if target is not None:
                if not isinstance(target, Detection):
                    raise ValueError("expected Detection or None")
                target.validate()
                if target.captured_at > now:
                    raise ValueError("capture time is in the future")
        except ValueError:
            self.fail()
            raise
        cfg = self.config
        dt = 0 if self._last_tick is None else min(now - self._last_tick, cfg.max_dt)
        self._last_tick = now
        fresh = (
            target is not None
            and target.confidence >= cfg.min_confidence
            and now - target.captured_at <= cfg.stale_after
            and (self._last_capture is None or target.captured_at > self._last_capture)
        )
        if not fresh:
            self._center_since = None
            if self._last_capture is not None:
                self._transition(
                    State.LOST if now - self._last_capture >= cfg.lost_after else State.TRACKING
                )
            return self._result("NO_FRESH_TARGET")
        # The preceding guard ensures target is a valid Detection.
        assert target is not None
        gap = (
            self._last_capture is not None
            and target.captured_at - self._last_capture > cfg.stale_after
        )
        self._last_capture = target.captured_at
        if gap:
            self._center_since = None
        ex = (target.x1 + target.x2) / target.width - 1
        ey = (target.y1 + target.y2) / target.height - 1
        centered = abs(ex) <= cfg.deadband and abs(ey) <= cfg.deadband
        if centered:
            if self._center_since is None:
                self._center_since = now
            self._transition(
                State.CENTERED if now - self._center_since >= cfg.dwell else State.TRACKING
            )
        else:
            self._center_since = None
            self._transition(State.TRACKING)
        for axis, error, sign, low, high in (
            ("_yaw", ex, cfg.yaw_sign, cfg.yaw_min, cfg.yaw_max),
            ("_pitch", ey, cfg.pitch_sign, cfg.pitch_min, cfg.pitch_max),
        ):
            if abs(error) > cfg.deadband:
                step = _clip(error * cfg.gain * sign, -cfg.max_rate, cfg.max_rate) * dt
                setattr(self, axis, _clip(getattr(self, axis) + step, low, high))
        return self._result("CENTERED" if self.state == State.CENTERED else "TARGET_UPDATE")

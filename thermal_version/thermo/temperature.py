"""Pure ROI statistics and validity FSM. No hardware imports."""

from collections import deque
from dataclasses import dataclass
from enum import Enum
import math
from statistics import median, mean


class State(str, Enum):
    INVALID = "INVALID"
    STABILIZING = "STABILIZING"
    COLLECTING = "COLLECTING"
    VALID = "VALID"


@dataclass(frozen=True)
class Reading:
    state: str
    reason: str
    value: float | None = None
    maximum: float | None = None
    average: float | None = None
    samples: int = 0
    acquired_at: float | None = None


def roi_stats(matrix, cfg):
    if (
        not isinstance(matrix, (list, tuple))
        or len(matrix) != 24
        or any(not isinstance(row, (list, tuple)) or len(row) != 32 for row in matrix)
    ):
        raise ValueError("BAD_MATRIX_SIZE")
    # Validate every input pixel, not only the displayed crop.
    if any(type(v) not in (int, float) for row in matrix for v in row):
        raise ValueError("BAD_PIXEL_TYPE")
    half = cfg.roi_size // 2
    values = [
        matrix[y][x]
        for y in range(cfg.roi_cy - half, cfg.roi_cy + half + 1)
        for x in range(cfg.roi_cx - half, cfg.roi_cx + half + 1)
    ]
    values = [
        v + cfg.temperature_offset
        for v in values
        if math.isfinite(v) and cfg.min_temperature <= v <= cfg.max_temperature
    ]
    required = math.ceil(cfg.roi_size**2 * cfg.min_valid_fraction)
    if len(values) < required:
        raise ValueError("TOO_FEW_VALID_PIXELS")
    mid = median(values)
    mad = median(abs(v - mid) for v in values)
    threshold = max(cfg.outlier_floor, cfg.outlier_mad * 1.4826 * mad)
    values = sorted(v for v in values if abs(v - mid) <= threshold)
    if len(values) < required:
        raise ValueError("TOO_MANY_OUTLIERS")
    index = 0.9 * (len(values) - 1)
    low = int(index)
    p90 = values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)
    return p90, max(values), mean(values)


def roi_covered(target, base, cfg):
    # Center-only calibration: selected RGB patch must cover the angular extent
    # of the IR ROI around the calibrated RGB aim point, not just be large.
    half_x = (
        cfg.roi_size
        / 32
        * math.tan(math.radians(cfg.ir_hfov / 2))
        / (2 * math.tan(math.radians(base.hfov_deg / 2)))
    )
    half_y = (
        cfg.roi_size
        / 24
        * math.tan(math.radians(cfg.ir_vfov / 2))
        / (2 * math.tan(math.radians(base.vfov_deg / 2)))
    )
    return (
        target.x1 / target.width <= base.aim_x - half_x
        and target.x2 / target.width >= base.aim_x + half_x
        and target.y1 / target.height <= base.aim_y - half_y
        and target.y2 / target.height >= base.aim_y + half_y
    )


class TemperatureGate:
    def __init__(self, cfg):
        self.cfg = cfg
        self._state = State.INVALID
        self.reason = "SELECT_EYE"
        self.session = None
        self.stable_since = None
        self.last_clock = None
        self.last_frame = None
        self.history = deque(maxlen=cfg.fusion_frames)
        self.reading = Reading(self._state.value, self.reason)

    @property
    def state(self):
        return self._state

    def _clear(self, reason):
        self._state = State.INVALID
        self.reason = reason
        self.stable_since = None
        self.history.clear()
        self.reading = Reading(self.state.value, reason)
        return self.reading

    def update(self, now, *, session, eligible, reason, frame=None):
        if (
            not math.isfinite(now)
            or now < 0
            or (self.last_clock is not None and now <= self.last_clock)
        ):
            self._clear("CLOCK_ERROR")
            raise ValueError("non-monotonic temperature clock")
        self.last_clock = now
        if session != self.session:
            self._clear("NEW_SELECTION")
            self.session = session
        if not eligible:
            return self._clear(reason)
        if self.stable_since is None:
            self.stable_since = now
        if now - self.stable_since < self.cfg.stabilization:
            self._state = State.STABILIZING
            self.reading = Reading(self.state.value, "CENTER_AND_HOLD")
            return self.reading
        if frame is not None:
            if not isinstance(frame, dict) or type(frame.get("captured_at")) not in (int, float):
                return self._clear("BAD_SENSOR_FRAME")
            captured = frame["captured_at"]
            if (
                not math.isfinite(captured)
                or captured > now
                or now - captured > self.cfg.sensor_timeout
            ):
                return self._clear("STALE_SENSOR")
            # Only frames acquired after stability begins may enter fusion.
            if captured < self.stable_since + self.cfg.stabilization:
                frame = None
            elif self.last_frame is not None and captured <= self.last_frame:
                if captured < self.last_frame:
                    return self._clear("OUT_OF_ORDER_SENSOR")
                frame = None
            else:
                self.last_frame = captured
                try:
                    stats = roi_stats(frame["matrix"], self.cfg)
                except (ValueError, KeyError, TypeError):
                    return self._clear("BAD_SENSOR_FRAME")
                if self.history and captured - self.history[-1][0] > self.cfg.sensor_timeout:
                    self.history.clear()
                self.history.append((captured, *stats))
        if self.history and now - self.history[-1][0] > self.cfg.sensor_timeout:
            return self._clear("STALE_SENSOR")
        if len(self.history) < self.cfg.fusion_frames:
            self._state = State.COLLECTING
            self.reading = Reading(self.state.value, "COLLECTING", samples=len(self.history))
        elif (
            max(x[1] for x in self.history) - min(x[1] for x in self.history)
            > self.cfg.temperature_span
        ):
            self._state = State.COLLECTING
            self.reading = Reading(
                self.state.value, "TEMPERATURE_UNSTABLE", samples=len(self.history)
            )
        else:
            self._state = State.VALID
            self.reading = Reading(
                self.state.value,
                "SURFACE_ONLY",
                mean(x[1] for x in self.history),
                self.history[-1][2],
                self.history[-1][3],
                len(self.history),
                self.history[-1][0],
            )
        return self.reading

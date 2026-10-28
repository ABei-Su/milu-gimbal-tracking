"""Single-target association and feedback-based image servo, independent of SDK."""

import math
from dataclasses import dataclass


def clamp(value, low, high):
    return max(low, min(high, value))


def center(d):
    return ((d.x1 + d.x2) / (2 * d.width), (d.y1 + d.y2) / (2 * d.height))


class TargetSelector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.previous = None
        self.last_seen = None
        self.last_strong = None
        self.last_frame = None
        self.generation = 0

    def select(self, detections, captured_at, now):
        if not all(math.isfinite(v) for v in (captured_at, now)) or captured_at > now:
            raise ValueError("invalid capture clock")
        if self.last_frame is not None and captured_at <= self.last_frame:
            return None, False
        self.last_frame = captured_at
        if now - captured_at > self.cfg.stale_after:
            return None, False
        strong, weak = [], []
        for d in detections:
            d.validate()
            if d.captured_at != captured_at:
                raise ValueError("mixed capture timestamps")
            if d.confidence >= self.cfg.confidence:
                strong.append(d)
            elif d.confidence >= self.cfg.track_confidence:
                weak.append(d)
        if self.last_seen is not None and now - self.last_seen > self.cfg.lock_timeout:
            self.previous = None
        if self.previous is None:
            if not strong:
                return None, False
            chosen = min(strong, key=lambda d: (-d.confidence, center(d)))
            self.generation += 1
            ambiguous = len(strong) > 1
        else:
            px, py = center(self.previous)

            def distance(d):
                x, y = center(d)
                return (x - px) ** 2 + (y - py) ** 2

            chosen = min(strong, key=distance, default=None)
            if chosen is not None and distance(chosen) <= self.cfg.association_radius**2:
                ambiguous = len(strong) > 1
            else:
                # Only fresh, overlapping evidence can bridge a short score dip.
                if self.last_strong is None or now - self.last_strong > self.cfg.stale_after:
                    return None, False
                compatible = [
                    d
                    for d in weak
                    if distance(d) <= self.cfg.association_radius**2
                    and overlaps_previous(self.previous, d)
                ]
                if len(compatible) != 1:
                    return None, False
                chosen = compatible[0]
                ambiguous = True  # weak continuity must never authorize the light
        self.previous = chosen
        self.last_seen = captured_at
        if chosen.confidence >= self.cfg.confidence:
            self.last_strong = captured_at
        return chosen, ambiguous


def overlaps_previous(previous, current):
    def box(d):
        return (d.x1 / d.width, d.y1 / d.height, d.x2 / d.width, d.y2 / d.height)

    a, b = box(previous), box(current)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1])
    )
    return 0.5 <= area_b / area_a <= 2 and intersection / (area_a + area_b - intersection) >= 0.3


@dataclass(frozen=True)
class Aim:
    yaw: float
    pitch: float
    centered: bool
    limited: bool


class VisualServo:
    """Quantization-aware floating reference with bounded, per-axis motion shaping.

    Velocity/acceleration describe the software reference, not measured motor
    motion. Loss, reference rebase and hard clamps override smoothness.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.last_time = None
        self.last_capture = None
        self.filtered = None
        self.reference = None
        self.velocity = [0.0, 0.0]
        self.acceleration = [0.0, 0.0]
        self.in_deadband = [False, False]
        self.generation = None
        self.rebase_reason = None

    def _rebase(self, measured, reason):
        self.reference = list(measured)
        self.velocity = [0.0, 0.0]
        self.acceleration = [0.0, 0.0]
        self.filtered = None
        self.last_capture = None
        self.in_deadband = [False, False]
        self.rebase_reason = reason

    def _filter(self, raw, captured):
        # A reused frame is not another measurement. Use acquisition intervals,
        # not the number of control ticks since the same picture arrived.
        if self.last_capture == captured:
            return
        if self.filtered is None:
            self.filtered = raw
        else:
            dt = captured - self.last_capture
            alpha = 1 - math.exp(-dt / self.cfg.smoothing_tau)
            self.filtered = tuple(a + alpha * (b - a) for a, b in zip(self.filtered, raw))
        self.last_capture = captured

    def _axis(self, i, error, measured, dt, fov, sign, limit):
        cfg = self.cfg
        if self.in_deadband[i]:
            if abs(error) > cfg.deadband + cfg.deadband_hysteresis:
                self.in_deadband[i] = False
        elif abs(error) <= cfg.deadband:
            self.in_deadband[i] = True

        # Taper gain near center; the motion shaper handles the remaining
        # request changes at the per-axis hysteresis edges.
        if self.in_deadband[i]:
            desired = 0.0
        else:
            if cfg.deadband:
                u = min(1.0, abs(error) / (2 * cfg.deadband))
                error *= u * u * (3 - 2 * u)
            angle = math.degrees(math.atan(2 * error * math.tan(math.radians(fov / 2))))
            desired = clamp(angle * cfg.gain * sign, -cfg.max_rate, cfg.max_rate)

        # Substep only the cheap scalar reference, never I/O or vision. Bounded
        # to 25 steps by max_control_gap <= .25. Avoid large-dt filter instability.
        steps = max(1, math.ceil(dt / 0.01))
        step = dt / steps
        limited = False
        for _ in range(steps):
            ref = self.reference[i]
            direction = 1 if desired >= 0 else -1
            remaining = max(
                0.0, min(limit - direction * ref, cfg.max_lead - direction * (ref - measured))
            )
            # Conservative speed envelope includes acceleration ramp time.
            ramp = cfg.max_accel * (cfg.max_accel / cfg.max_jerk + cfg.velocity_tau)
            approach_rate = max(0.0, math.sqrt(ramp * ramp + 2 * cfg.max_accel * remaining) - ramp)
            request = clamp(desired, -approach_rate, approach_rate)
            wanted_accel = clamp(
                (request - self.velocity[i]) / cfg.velocity_tau,
                -cfg.max_accel,
                cfg.max_accel,
            )
            acceleration = clamp(
                wanted_accel,
                self.acceleration[i] - cfg.max_jerk * step,
                self.acceleration[i] + cfg.max_jerk * step,
            )
            old_rate = self.velocity[i]
            proposed_rate = old_rate + acceleration * step
            rate = clamp(proposed_rate, -cfg.max_rate, cfg.max_rate)
            if rate != proposed_rate:
                acceleration = 0.0
                limited = True
            goal = ref + (old_rate + rate) * step / 2
            low = max(-limit, measured - cfg.max_lead)
            high = min(limit, measured + cfg.max_lead)
            bounded = clamp(goal, low, high)
            if abs(goal - bounded) > 1e-10:
                # No latent integrator energy at a blocked actuator/hard limit.
                rate = acceleration = 0.0
                limited = True
            self.reference[i] = bounded
            self.velocity[i], self.acceleration[i] = rate, acceleration
        return limited or abs(measured) >= limit

    def update(self, target, now, measured, generation):
        if (
            len(measured) != 2
            or not math.isfinite(now)
            or now < 0
            or any(not math.isfinite(v) for v in measured)
        ):
            raise ValueError("invalid control input")
        if self.last_time is not None and now <= self.last_time:
            raise ValueError("non-monotonic servo clock")
        elapsed = 0 if self.last_time is None else now - self.last_time
        self.last_time = now
        self.rebase_reason = None
        limits = (self.cfg.yaw_limit, self.cfg.pitch_limit)
        # The device layer separately faults on significant feedback overshoot.
        bounded_measured = tuple(clamp(v, -lim, lim) for v, lim in zip(measured, limits))
        if target is not None:
            target.validate()
            if target.captured_at > now:
                raise ValueError("future detection")
        if target is None or now - target.captured_at > self.cfg.stale_after:
            self._rebase(bounded_measured, "target_lost")
            self.generation = generation
            return Aim(*self.reference, False, bounded_measured != tuple(measured))
        if self.last_capture is not None and target.captured_at < self.last_capture:
            self._rebase(bounded_measured, "out_of_order")
            return Aim(*self.reference, False, False)
        if elapsed > self.cfg.max_control_gap:
            self._rebase(bounded_measured, "control_gap")
            self.generation = generation
            return Aim(*self.reference, False, False)
        if self.reference is None or generation != self.generation:
            self._rebase(bounded_measured, "target_changed")
            self.generation = generation
            elapsed = 0.0
        if any(abs(r - m) > self.cfg.max_lead + 0.1 for r, m in zip(self.reference, measured)):
            self._rebase(bounded_measured, "feedback_discontinuity")
            return Aim(*self.reference, False, True)

        cx, cy = center(target)
        raw = (cx - self.cfg.aim_x, cy - self.cfg.aim_y)
        self._filter(raw, target.captured_at)
        limited = bounded_measured != tuple(measured)
        for i, (fov, sign, limit) in enumerate(
            zip(
                (self.cfg.hfov_deg, self.cfg.vfov_deg),
                (self.cfg.yaw_sign, self.cfg.pitch_sign),
                limits,
            )
        ):
            limited |= self._axis(
                i, self.filtered[i], bounded_measured[i], elapsed, fov, sign, limit
            )
        # Being in the image center alone does not mean deceleration is finished.
        centered = (
            max(abs(v) for v in raw) <= self.cfg.deadband
            and max(abs(v) for v in self.velocity) <= self.cfg.settle_rate
        )
        return Aim(*self.reference, centered, limited)


class TargetStream:
    """Hold the latest measurement only until its acquisition-time TTL expires."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.selector = TargetSelector(cfg)
        self.target = None
        self.ambiguous = False

    @property
    def generation(self):
        return self.selector.generation

    def update(self, message, now):
        if message is not None:
            self.target, self.ambiguous = self.selector.select(
                message["detections"], message["captured_at"], now
            )
        if self.target is None or now - self.target.captured_at > self.cfg.stale_after:
            return None, False
        if self.target.confidence < self.cfg.confidence and (
            self.selector.last_strong is None
            or now - self.selector.last_strong > self.cfg.stale_after
        ):
            return None, False
        return self.target, self.ambiguous

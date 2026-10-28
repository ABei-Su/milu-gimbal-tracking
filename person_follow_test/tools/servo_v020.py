"""Frozen 0.2.0 baseline for offline comparison only; never import on board."""

import math
from milu.targeting import Aim, clamp, center


class VisualServo:
    def __init__(self, cfg):
        self.cfg = cfg
        self.last_time = None
        self.filtered = None
        self.velocity = [0.0, 0.0]
        self.generation = None

    def update(self, target, now, measured, generation):
        if not math.isfinite(now) or any(not math.isfinite(v) for v in measured):
            raise ValueError("non-finite control input")
        if self.last_time is not None and now <= self.last_time:
            raise ValueError("non-monotonic servo clock")
        dt = 0 if self.last_time is None else min(now - self.last_time, 0.1)
        self.last_time = now
        if generation != self.generation:
            self.filtered = None
            self.velocity = [0.0, 0.0]
            self.generation = generation
        if target is None or now - target.captured_at > self.cfg.stale_after:
            self.velocity = [0.0, 0.0]
            self.filtered = None
            return Aim(*measured, False, False)
        target.validate()
        if target.captured_at > now:
            raise ValueError("future detection")
        cx, cy = center(target)
        raw = (cx - self.cfg.aim_x, cy - self.cfg.aim_y)
        if self.filtered is None:
            self.filtered = raw
        else:
            alpha = 1 - math.exp(-dt / self.cfg.smoothing_tau)
            self.filtered = tuple(old + alpha * (new - old) for old, new in zip(self.filtered, raw))
        centered = max(abs(v) for v in raw) <= self.cfg.deadband
        result = []
        limited = False
        for i, (error, fov, sign, limit) in enumerate(
            zip(
                self.filtered,
                (self.cfg.hfov_deg, self.cfg.vfov_deg),
                (self.cfg.yaw_sign, self.cfg.pitch_sign),
                (self.cfg.yaw_limit, self.cfg.pitch_limit),
            )
        ):
            # Angle from calibrated pinhole FOV; no integral accumulation.
            angle = math.degrees(math.atan(2 * error * math.tan(math.radians(fov / 2))))
            desired_rate = (
                0.0
                if centered
                else clamp(angle * self.cfg.gain * sign, -self.cfg.max_rate, self.cfg.max_rate)
            )
            dv = self.cfg.max_accel * dt
            rate = clamp(desired_rate, self.velocity[i] - dv, self.velocity[i] + dv)
            if centered:
                rate = 0.0
            goal = measured[i] + rate * dt
            bounded = clamp(goal, -limit, limit)
            limited |= abs(goal - bounded) > 1e-8 or abs(measured[i]) >= limit
            self.velocity[i] = 0.0 if goal != bounded else rate
            result.append(bounded)
        return Aim(*result, centered, limited)

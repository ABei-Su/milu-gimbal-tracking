# Frozen 0.3 selector for offline comparison.
import math
from milu.targeting import center


class TargetSelector:
    def __init__(self, cfg):
        self.cfg = cfg
        self.previous = None
        self.last_seen = None
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
        valid = []
        for d in detections:
            d.validate()
            if d.captured_at != captured_at:
                raise ValueError("mixed capture timestamps")
            if d.confidence >= self.cfg.confidence:
                valid.append(d)
        if self.last_seen is not None and now - self.last_seen > self.cfg.lock_timeout:
            self.previous = None
        if not valid:
            return None, False
        if self.previous is None:
            valid.sort(key=lambda d: (-d.confidence, center(d)))
            chosen = valid[0]
            self.generation += 1
            ambiguous = len(valid) > 1
        else:
            px, py = center(self.previous)
            ranked = sorted(
                (math.hypot(center(d)[0] - px, center(d)[1] - py), i, d)
                for i, d in enumerate(valid)
            )
            if ranked[0][0] > self.cfg.association_radius:
                return None, False
            chosen = ranked[0][2]
            ambiguous = len(ranked) > 1
        self.previous = chosen
        self.last_seen = captured_at
        return chosen, ambiguous

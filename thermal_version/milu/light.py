"""Paper-target light state machine. GPIO ownership stays in the main process."""

import math
from enum import Enum


class LightState(str, Enum):
    DISARMED = "disarmed"
    WAITING = "waiting"
    PULSE = "pulse"
    COOLDOWN = "cooldown"
    FAULT = "fault"


class LightGate:
    def __init__(self, cfg, paper_mode=False):
        self.cfg = cfg
        self.paper_mode = paper_mode
        self._state = LightState.WAITING if paper_mode else LightState.DISARMED
        self.stable_since = None
        self.pulse_since = None
        self.next_allowed = 0.0
        self.last_time = None
        self.generation = None

    @property
    def state(self):
        return self._state

    def fault(self):
        self._state = LightState.FAULT
        self.stable_since = None
        return False

    def update(self, now, *, eligible, generation):
        if (
            not math.isfinite(now)
            or now < 0
            or (self.last_time is not None and now <= self.last_time)
        ):
            self.fault()
            raise ValueError("invalid light clock")
        self.last_time = now
        if self.state in (LightState.DISARMED, LightState.FAULT):
            return False
        if generation != self.generation:
            self.generation = generation
            eligible = False
        if not eligible:
            if self.state == LightState.PULSE:
                self.next_allowed = now + self.cfg.laser_cooldown
            self.stable_since = None
            self._state = LightState.COOLDOWN if now < self.next_allowed else LightState.WAITING
            return False
        if self.state == LightState.PULSE:
            if now - self.pulse_since >= self.cfg.laser_pulse:
                self.next_allowed = now + self.cfg.laser_cooldown
                self.stable_since = None
                self._state = LightState.COOLDOWN
                return False
            return True
        if now < self.next_allowed:
            self._state = LightState.COOLDOWN
            self.stable_since = None
            return False
        self._state = LightState.WAITING
        if self.stable_since is None:
            self.stable_since = now
        if now - self.stable_since >= self.cfg.dwell:
            self._state = LightState.PULSE
            self.pulse_since = now
            return True
        return False

"""Strict settings boundary; all angles in degrees, times in seconds."""

import json
import math
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    model: str = "models/milu.mud"
    uart_device: str = "/dev/ttyS4"
    tx_pin: str = "A21"
    rx_pin: str = "A22"
    tx_function: str = "UART4_TX"
    rx_function: str = "UART4_RX"
    laser_pin: str = "A4"
    laser_active_high: bool = True
    yaw_sign: int = -1
    pitch_sign: int = 1
    yaw_limit: float = 10.0
    pitch_limit: float = 10.0
    position_rpm: int = 30
    frame_gap: float = 0.002
    query_timeout: float = 0.08
    feedback_timeout: float = 0.5
    boot_wait: float = 1.5
    loop_hz: float = 20.0
    confidence: float = 0.65
    track_confidence: float = 0.4
    nms_iou: float = 0.45
    stale_after: float = 0.25
    lock_timeout: float = 0.5
    association_radius: float = 0.25
    smoothing_tau: float = 0.06
    hfov_deg: float = 60.0
    vfov_deg: float = 45.0
    gain: float = 1.8
    max_rate: float = 12.0
    max_accel: float = 60.0
    max_jerk: float = 400.0
    velocity_tau: float = 0.15
    max_lead: float = 2.0
    max_control_gap: float = 0.2
    deadband_hysteresis: float = 0.008
    settle_rate: float = 0.25
    deadband: float = 0.02
    aim_x: float = 0.5
    aim_y: float = 0.5
    dwell: float = 0.5
    reached_tolerance: float = 0.3
    laser_pulse: float = 0.15
    laser_cooldown: float = 2.0
    paper_roi: tuple = (0.1, 0.1, 0.9, 0.9)
    show_display: bool = True

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name in ("laser_active_high", "show_display"):
                if type(value) is not bool:
                    raise ValueError(f"{f.name} must be boolean")
            elif f.name == "paper_roi":
                if not isinstance(value, (tuple, list)) or len(value) != 4:
                    raise ValueError("paper_roi requires four normalized coordinates")
                if not all(type(v) in (int, float) and math.isfinite(v) for v in value):
                    raise ValueError("paper_roi is not finite")
                x1, y1, x2, y2 = value
                if not 0 <= x1 < x2 <= 1 or not 0 <= y1 < y2 <= 1:
                    raise ValueError("paper_roi outside image")
                object.__setattr__(self, f.name, tuple(value))
            elif isinstance(f.default, str):
                if not isinstance(value, str) or not value:
                    raise ValueError(f"{f.name} must be nonempty text")
            elif type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{f.name} must be finite numeric")
        if self.yaw_sign not in (-1, 1) or self.pitch_sign not in (-1, 1):
            raise ValueError("axis signs must be -1/+1")
        if type(self.position_rpm) is not int or not 1 <= self.position_rpm <= 30:
            raise ValueError("prototype position_rpm must be integer 1..30")
        for name in ("yaw_limit", "pitch_limit"):
            if not 0.1 <= getattr(self, name) <= 90:
                raise ValueError("limits must be 0.1..90 degrees")
        for name in ("confidence", "track_confidence", "nms_iou"):
            if not 0 < getattr(self, name) < 1:
                raise ValueError(f"{name} must be 0..1 exclusive")
        for name in (
            "gain",
            "max_rate",
            "max_accel",
            "smoothing_tau",
            "dwell",
            "reached_tolerance",
            "stale_after",
            "lock_timeout",
            "association_radius",
            "laser_cooldown",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if not (0.002 <= self.frame_gap <= 0.05 and 0.01 <= self.query_timeout <= 0.2):
            raise ValueError("invalid UART timing")
        if not (0.2 <= self.feedback_timeout <= 1 and 1.5 <= self.boot_wait <= 10):
            raise ValueError("invalid startup/feedback timing")
        if not 5 <= self.loop_hz <= 50:
            raise ValueError("loop_hz must be 5..50")
        if not (1 <= self.hfov_deg < 170 and 1 <= self.vfov_deg < 170):
            raise ValueError("invalid field of view")
        if not (0 <= self.deadband <= 0.1 and 0.05 <= self.laser_pulse <= 0.5):
            raise ValueError("invalid deadband/pulse")
        if not (0.1 <= self.aim_x <= 0.9 and 0.1 <= self.aim_y <= 0.9):
            raise ValueError("aim point outside central image")
        if self.stale_after > self.lock_timeout or self.max_rate > self.position_rpm * 6:
            raise ValueError("inconsistent timeout or speed")
        if not (10 <= self.max_jerk <= 5000 and 0.05 <= self.velocity_tau <= 1):
            raise ValueError("invalid trajectory jerk/response")
        if not (0.1 <= self.max_lead <= 5 and 0.1 <= self.max_control_gap <= 0.25):
            raise ValueError("invalid reference lead/control gap")
        if not (0 <= self.deadband_hysteresis <= 0.05 and 0 < self.settle_rate <= 1):
            raise ValueError("invalid hysteresis/settle rate")
        if self.max_control_gap < 1 / self.loop_hz:
            raise ValueError("control gap shorter than loop period")
        if len({self.tx_pin, self.rx_pin, self.laser_pin}) != 3:
            raise ValueError("UART and laser pins conflict")


def load_settings(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("settings must be an object")
    return Settings(**data)

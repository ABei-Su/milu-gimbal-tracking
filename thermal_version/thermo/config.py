"""Thermal hardware profile and measurement settings; unknown seller protocol is rejected."""

import json
import math
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class ThermalConfig:
    sensor_backend: str = "pending_uart"
    sensor_confirmed: bool = False
    alignment_confirmed: bool = False
    tracker_model: str = "/root/models/mixformer_v2.mud"
    tracker_threshold: float = 0.75
    i2c_bus: int = 6
    sda_pin: str = "A0"
    scl_pin: str = "A1"
    sda_function: str = "I2C6_SDA"
    scl_function: str = "I2C6_SCL"
    sensor_fps: int = 8
    emissivity: float = 0.95
    roi_size: int = 3
    roi_cx: int = 16
    roi_cy: int = 12
    ir_hfov: float = 110.0
    ir_vfov: float = 75.0
    fusion_frames: int = 5
    sensor_timeout: float = 0.6
    status_timeout: float = 0.25
    stabilization: float = 0.6
    min_temperature: float = -40.0
    max_temperature: float = 300.0
    temperature_offset: float = 0.0
    outlier_floor: float = 2.0
    outlier_mad: float = 3.5
    min_valid_fraction: float = 0.8
    temperature_span: float = 2.0
    measured_settle_rate: float = 0.5
    max_box_jump: float = 0.2

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(f.default, bool):
                if type(value) is not bool:
                    raise ValueError(f.name + " must be bool")
            elif isinstance(f.default, str):
                if not isinstance(value, str) or not value:
                    raise ValueError(f.name + " requires text")
            elif type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f.name + " requires finite number")
        for key in ("i2c_bus", "sensor_fps", "roi_size", "roi_cx", "roi_cy", "fusion_frames"):
            if type(getattr(self, key)) is not int:
                raise ValueError(key + " must be integer")
        if self.sensor_backend not in ("mlx90640_i2c", "pending_uart"):
            raise ValueError("Unknown module protocol: UART requires the seller specification")
        if not 0 <= self.i2c_bus <= 7 or self.sensor_fps not in (1, 2, 4, 8, 16):
            raise ValueError("unsupported sensor bus/FPS")
        if self.sensor_timeout < 2 / self.sensor_fps or self.sensor_timeout > 5:
            raise ValueError("timeout must accommodate both sensor subpages")
        if self.roi_size not in (3, 5) or not 5 <= self.fusion_frames <= 10:
            raise ValueError("ROI must be 3/5 and fusion frames 5..10")
        half = self.roi_size // 2
        if not half <= self.roi_cx < 32 - half or not half <= self.roi_cy < 24 - half:
            raise ValueError("ROI outside thermal matrix")
        if not 0.1 <= self.emissivity <= 1 or not 0 < self.tracker_threshold < 1:
            raise ValueError("invalid emissivity/tracker threshold")
        if not 1 < self.ir_hfov < 170 or not 1 < self.ir_vfov < 170:
            raise ValueError("invalid thermal FOV")
        if not -40 <= self.min_temperature < self.max_temperature <= 300:
            raise ValueError("invalid thermal range")
        if not abs(self.temperature_offset) <= 10:
            raise ValueError("offset requires calibrated range")
        if not 0.05 <= self.status_timeout <= 1 or not 0.1 <= self.stabilization <= 5:
            raise ValueError("invalid state timing")
        if not 0.5 <= self.min_valid_fraction <= 1 or not 0 < self.max_box_jump <= 0.5:
            raise ValueError("invalid valid-pixel/box fraction")
        for name in ("outlier_floor", "outlier_mad", "temperature_span", "measured_settle_rate"):
            if getattr(self, name) <= 0:
                raise ValueError(name + " must be positive")

    def check_pins(self, base):
        pins = (self.sda_pin, self.scl_pin, base.tx_pin, base.rx_pin, base.laser_pin)
        if len(set(pins)) != len(pins):
            raise ValueError("thermal pins conflict with UART/GPIO")


def load_config(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("thermal config requires an object")
    return ThermalConfig(**data)

"""MaixCAM2 hardware boundary; imported on the board only when used."""

import os
import select
import time
from pathlib import Path


def check_board():
    from maix import sys as maix_sys

    if maix_sys.device_id() != "maixcam2":
        raise RuntimeError("This adapter requires MaixCAM2. Change adapters for other boards.")


def map_pin(pin, function):
    from maix import pinmap, err

    err.check_raise(pinmap.set_pin_function(pin, function), f"pinmap failed: {pin} -> {function}")


class SerialTransport:
    """Linux nonblocking UART. One system write per complete F32C frame."""

    def __init__(self, cfg):
        import termios

        check_board()
        self.cfg = cfg
        self.termios = termios
        map_pin(cfg.tx_pin, cfg.tx_function)
        map_pin(cfg.rx_pin, cfg.rx_function)
        if not cfg.uart_device.startswith("/dev/ttyS"):
            raise ValueError("expected a board /dev/ttyS UART")
        self.fd = os.open(cfg.uart_device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            attrs = termios.tcgetattr(self.fd)
            attrs[0] = attrs[1] = attrs[3] = 0
            attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
            attrs[4] = attrs[5] = termios.B115200
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
            self.clear_input()
        except Exception:
            os.close(self.fd)
            self.fd = None
            raise
        self.next_write = 0.0

    def send(self, frame):
        if self.fd is None:
            raise OSError("UART closed")
        delay = self.next_write - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        _, ready, _ = select.select([], [self.fd], [], self.cfg.query_timeout)
        if not ready:
            raise TimeoutError("UART_TX_TIMEOUT")
        count = os.write(self.fd, frame)
        self.next_write = time.monotonic() + len(frame) * 10 / 115200 + self.cfg.frame_gap
        if count != len(frame):
            raise OSError(f"UART_PARTIAL_FRAME {count}/{len(frame)}; no fragment retry")

    def read(self):
        if not select.select([self.fd], [], [], 0)[0]:
            return b""
        try:
            return os.read(self.fd, 256)
        except BlockingIOError:
            return b""

    def clear_input(self):
        self.termios.tcflush(self.fd, self.termios.TCIFLUSH)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class LaserOutput:
    def __init__(self, cfg):
        from maix import gpio

        check_board()
        self.off_level = 0 if cfg.laser_active_high else 1
        name = "GPIO" + cfg.laser_pin
        map_pin(cfg.laser_pin, name)
        pull = gpio.Pull.PULL_DOWN if cfg.laser_active_high else gpio.Pull.PULL_UP
        self.pin = gpio.GPIO(name, gpio.Mode.OUT, pull)
        self.set(False)

    def set(self, on):
        value = 1 - self.off_level if on else self.off_level
        self.pin.value(value)


def verify_model(path):
    import configparser

    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Missing MaixCAM2 model: {path}; see docs/model-training.md")
    config = configparser.ConfigParser()
    config.read(path, encoding="utf-8")
    if config.get("basic", "type", fallback="") != "axmodel":
        raise ValueError("MaixCAM2 requires type=axmodel, not cvimodel/kmodel/pt")
    if config.get("extra", "model_type", fallback="") != "yolo11":
        raise ValueError("This adapter expects YOLO11 detector metadata")
    labels = [s.strip() for s in config.get("extra", "labels").split(",")]
    if "milu" not in labels:
        raise ValueError("Model must contain a trained 'milu' class; do not relabel a COCO model")
    for key in ("model_npu", "model_vnpu"):
        filename = config.get("basic", key)
        model = (path.parent / filename).resolve()
        if not model.is_relative_to(path.parent) or not model.is_file():
            raise FileNotFoundError(f"Missing/local-only {key}: {model}")
    return str(path)

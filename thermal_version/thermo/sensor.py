"""Official MaixPy MLX90640 I2C adapter isolated in a supervised process."""

import time
from milu.maixcam2 import map_pin, check_board
from milu.vision import publish_latest


def open_sensor(cfg):
    if cfg.sensor_backend == "pending_uart":
        raise ValueError("VENDOR_UART_PROTOCOL_REQUIRED")
    if not cfg.sensor_confirmed:
        raise ValueError("CONFIRM_SENSOR_TYPE: do not connect an unknown UART module to I2C")
    check_board()
    from maix import ext_dev

    map_pin(cfg.sda_pin, cfg.sda_function)
    map_pin(cfg.scl_pin, cfg.scl_function)
    fps = getattr(ext_dev.mlx90640.FPS, "FPS_" + str(cfg.sensor_fps))
    return ext_dev.mlx90640.MLX90640Celsius(
        cfg.i2c_bus, fps, ext_dev.cmap.Cmap.WHITE_HOT, -1, -1, cfg.emissivity
    )


def worker(cfg, channel, stop):
    try:
        sensor = open_sensor(cfg)
        while not stop.is_set():
            started = time.monotonic()
            matrix = sensor.matrix()
            if not matrix:
                raise OSError("EMPTY_THERMAL_MATRIX")
            publish_latest(channel, {"kind": "thermal", "captured_at": started, "matrix": matrix})
            # Vendor acquisition may wait for subpages; never put it in motor loop.
            stop.wait(max(0, 1 / cfg.sensor_fps - (time.monotonic() - started)))
    except Exception as exc:
        publish_latest(channel, {"kind": "sensor_error", "message": f"{type(exc).__name__}: {exc}"})
        # Wait for orderly parent teardown so the error can reach the queue feeder.
        stop.wait(2)

"""Bounded sensor-only diagnostic. Never opens camera, gimbal UART or laser GPIO."""

import argparse
import json
import logging
import math
import multiprocessing as mp
from pathlib import Path
import queue
import time
from thermo.config import load_config
from thermo.sensor import worker
from thermo.temperature import roi_stats
from thermo.runtime import stop_process


def collect(channel, process, cfg, count, timeout, clock=time.monotonic):
    if type(count) is not int or not 1 <= count <= 100:
        raise ValueError("frames must be 1..100")
    if not math.isfinite(timeout) or not 1 <= timeout <= 60:
        raise ValueError("timeout must be 1..60 seconds")
    started = clock()
    deadline = started + timeout
    rows = []
    last = None
    while len(rows) < count:
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError("SENSOR_PROBE_TIMEOUT")
        try:
            message = channel.get(timeout=min(0.2, remaining))
        except queue.Empty:
            if not process.is_alive():
                raise RuntimeError("SENSOR_WORKER_EXITED")
            continue
        if message.get("kind") == "sensor_error":
            raise RuntimeError(message["message"])
        acquired = message["captured_at"]
        now = clock()
        if now > deadline:
            raise TimeoutError("SENSOR_PROBE_TIMEOUT")
        if (
            type(acquired) not in (int, float)
            or not math.isfinite(acquired)
            or not 0 <= now - acquired <= cfg.sensor_timeout
        ):
            raise ValueError("STALE_SENSOR")
        if last is not None and acquired <= last:
            raise ValueError("REPEATED_OR_REORDERED_FRAME")
        p90, maximum, average = roi_stats(message["matrix"], cfg)
        values = [v for row in message["matrix"] for v in row]
        if not all(
            math.isfinite(v) and cfg.min_temperature <= v <= cfg.max_temperature for v in values
        ):
            raise ValueError("BAD_FULL_FRAME")
        rows.append(
            {
                "sample": len(rows) + 1,
                "acquired_at": acquired,
                "read_age_s": now - acquired,
                "global_min_c": min(values),
                "global_max_c": max(values),
                "roi_p90_c": p90,
                "roi_max_c": maximum,
                "roi_mean_c": average,
            }
        )
        last = acquired
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default=str(Path(__file__).resolve().parents[1] / "thermal.json")
    )
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=15)
    args = parser.parse_args()
    if (
        not 1 <= args.frames <= 100
        or not math.isfinite(args.timeout)
        or not 1 <= args.timeout <= 60
    ):
        parser.error("frames: 1..100; timeout: 1..60 seconds")
    cfg = load_config(args.config)
    if cfg.sensor_backend != "mlx90640_i2c" or not cfg.sensor_confirmed:
        parser.error("confirmed I2C sensor profile required")
    context = mp.get_context("spawn")
    stop = context.Event()
    channel = context.Queue(maxsize=1)
    process = context.Process(target=worker, args=(cfg, channel, stop), daemon=True)
    try:
        process.start()
        rows = collect(channel, process, cfg, args.frames, args.timeout)
        print(
            json.dumps(
                {
                    "profile": "MLX90640 I2C 0x33",
                    "samples": rows,
                    "note": "Sensor data only; RGB alignment and accuracy are not verified.",
                },
                indent=2,
            )
        )
        return 0
    finally:
        stop.set()
        try:
            stop_process(process, logging.getLogger(__name__))
        finally:
            channel.cancel_join_thread()
            channel.close()


if __name__ == "__main__":
    raise SystemExit(main())

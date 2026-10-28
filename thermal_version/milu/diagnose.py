"""Board preflight plus an explicit bounded single-axis direction check."""

import argparse
from pathlib import Path
import time
from milu.settings import load_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--jog-axis", choices=("yaw", "pitch"))
    parser.add_argument("--delta", type=float, default=1.0)
    args = parser.parse_args()
    if not -2 <= args.delta <= 2 or args.delta == 0:
        parser.error("delta must be nonzero and within +/-2 degrees")
    cfg = load_settings(args.config)
    from milu.maixcam2 import check_board, verify_model, LaserOutput, SerialTransport

    check_board()
    root = Path(args.config).resolve().parent
    print("Board: MaixCAM2")
    print("Model:", verify_model(root / cfg.model))
    from maix import pinmap

    print("UART mapping:", cfg.tx_pin, cfg.tx_function, cfg.rx_pin, cfg.rx_function)
    print(
        "Available pin functions:",
        pinmap.get_pin_functions(cfg.tx_pin),
        pinmap.get_pin_functions(cfg.rx_pin),
    )
    if not args.jog_axis:
        print("Read-only preflight finished. No UART/GPIO device was opened.")
        return
    from milu.gimbal import Gimbal

    laser = LaserOutput(cfg)
    device = None
    try:
        device = Gimbal(SerialTransport(cfg), cfg)
        device.start()
        started = time.monotonic()
        reached = False
        while time.monotonic() - started < 3:
            measured = device.poll()
            progress = min(abs(args.delta), (time.monotonic() - started) * 1.0)
            goal = progress if args.delta > 0 else -progress
            yaw, pitch = (goal, 0) if args.jog_axis == "yaw" else (0, goal)
            device.move(yaw, pitch)
            print("feedback", measured, "goal", (yaw, pitch))
            index = 0 if args.jog_axis == "yaw" else 1
            if (
                progress == abs(args.delta)
                and abs(measured[index] - args.delta) <= cfg.reached_tolerance
            ):
                reached = True
                break
            time.sleep(0.05)
        if not reached:
            raise TimeoutError("jog did not reach target")
    finally:
        try:
            laser.set(False)
        finally:
            if device:
                device.close()


if __name__ == "__main__":
    main()

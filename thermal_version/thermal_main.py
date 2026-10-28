"""Touchscreen eye-tracking/temperature entry; original modes are available through base_main.py."""

import argparse
import math
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(root / "thermal_gimbal.json"))
    parser.add_argument("--thermal-config", default=str(root / "thermal.json"))
    parser.add_argument("--seconds", type=float, default=0)
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds < 0:
        parser.error("seconds must be nonnegative")
    from thermo.runtime import run

    run(args.config, args.thermal_config, args.seconds)


if __name__ == "__main__":
    main()

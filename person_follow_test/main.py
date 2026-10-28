"""MaixVision application entry. Run on MaixCAM2, not on the F32C motor."""

import argparse
import math
from pathlib import Path

# Face tracking with interruptible startup search, as configured.
RUN_MODE = "track"


def main():
    parser = argparse.ArgumentParser(description="MaixCAM2 person following test; laser disabled")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--mode", choices=("observe", "track", "diagnose"), default=RUN_MODE)
    parser.add_argument("--seconds", type=float, default=0, help="0 means run until stopped")
    args = parser.parse_args()
    print("[BUILD] v1.0.0 | yaw-gentle-v2 frozen", flush=True)
    if not math.isfinite(args.seconds) or args.seconds < 0:
        parser.error("--seconds must be nonnegative")
    if args.mode == "diagnose":
        from milu.diagnostics import run as diagnose

        diagnose(args.config)
        return
    from milu.runtime import run

    run(args.config, args.mode, args.seconds)


if __name__ == "__main__":
    main()

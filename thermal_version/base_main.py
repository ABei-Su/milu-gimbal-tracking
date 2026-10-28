"""MaixVision application entry. Run on MaixCAM2, not on the F32C motor."""

import argparse
import math
from pathlib import Path

# MaixVision Run without arguments uses this mode. Change to track or paper
# after detection-only and wiring verification. CLI --mode overrides it.
RUN_MODE = "observe"


def main():
    parser = argparse.ArgumentParser(
        description="Milu MaixCAM2 tracking and paper-target indicator"
    )
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.json")))
    parser.add_argument("--mode", choices=("observe", "track", "paper"), default=RUN_MODE)
    parser.add_argument("--seconds", type=float, default=0, help="0 means run until stopped")
    args = parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds < 0:
        parser.error("--seconds must be nonnegative")
    from milu.runtime import run

    run(args.config, args.mode, args.seconds)


if __name__ == "__main__":
    main()

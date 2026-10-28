"""Write a separate calibrated configuration from a measured paper-target spot."""

import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from milu.settings import Settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--output", default="config.calibrated.json")
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--spot-x", type=float, required=True)
    parser.add_argument("--spot-y", type=float, required=True)
    args = parser.parse_args()
    if (
        args.width <= 0
        or args.height <= 0
        or not all(math.isfinite(v) for v in (args.spot_x, args.spot_y))
    ):
        parser.error("invalid image or spot")
    source, output = Path(args.config).resolve(), Path(args.output).resolve()
    if source == output or output.exists():
        parser.error("choose a new output file; source configuration is preserved")
    data = json.loads(source.read_text(encoding="utf-8"))
    data.update(aim_x=args.spot_x / args.width, aim_y=args.spot_y / args.height)
    Settings(**data)
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

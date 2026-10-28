"""Plot benchmark traces; requires the optional PC training environment."""

import csv
from pathlib import Path
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/smooth_servo"


def load(name, version):
    with (OUT / (name + "_" + version + ".csv")).open() as stream:
        return [
            {k: float(v) for k, v in row.items() if k not in ("centered", "limited")}
            for row in csv.DictReader(stream)
        ]


def main():
    fig, axes = plt.subplots(2, 2, figsize=(12, 6.5), sharex="col", constrained_layout=True)
    for col, (name, title) in enumerate(
        (
            ("moving_low_fps", "Moving target: 8 FPS, 100 ms latency"),
            ("near_limit", "Soft-limit approach and return"),
        )
    ):
        for version, color in (("v0.2", "#94a3b8"), ("v0.3", "#087f8c")):
            rows = load(name, version)
            time = [r["time"] for r in rows]
            axes[0, col].plot(
                time, [r["ref_yaw"] for r in rows], label=version, color=color, lw=1.5
            )
            axes[1, col].plot(
                time, [r["rate_yaw"] for r in rows], label=version, color=color, lw=1.5
            )
        axes[0, col].set_title(title)
        axes[0, col].set_ylabel("Yaw reference (deg)")
        axes[1, col].set_ylabel("Reference velocity (deg/s)")
        axes[1, col].set_xlabel("Time (s)")
        for row in (0, 1):
            axes[row, col].grid(alpha=0.2)
            axes[row, col].legend(frameon=False)
    fig.suptitle(
        "Software-in-the-loop comparison: assumed motor dynamics, NOT hardware measurements"
    )
    fig.savefig(OUT / "comparison.png", dpi=150)
    fig.savefig(OUT / "comparison.svg")
    print(OUT / "comparison.png")


if __name__ == "__main__":
    main()

"""Deterministic SIL comparison; assumed plant, not measured F32C dynamics."""

import argparse
import csv
import json
import math
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from milu.settings import Settings
from milu.targeting import VisualServo
from milu.tracking import Detection
from tools.servo_v020 import VisualServo as Baseline

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = {
    "static_noisy": {"kind": "step", "noise": 2.5, "fps": 10, "delay": 0.08, "plant_tau": 0.08},
    "static_slow_motor": {"kind": "step", "noise": 1, "fps": 10, "delay": 0.1, "plant_tau": 0.18},
    "moving": {"kind": "sine", "noise": 1.5, "fps": 15, "delay": 0.06, "plant_tau": 0.08},
    "moving_low_fps": {"kind": "sine", "noise": 2.5, "fps": 8, "delay": 0.1, "plant_tau": 0.12},
    "dropout": {
        "kind": "sine",
        "noise": 1,
        "fps": 10,
        "delay": 0.08,
        "plant_tau": 0.08,
        "drop": True,
    },
    "near_limit": {"kind": "limit", "noise": 1, "fps": 10, "delay": 0.08, "plant_tau": 0.08},
    "slow_precision": {
        "kind": "step",
        "noise": 0,
        "fps": 20,
        "delay": 0.05,
        "plant_tau": 0.04,
        "slow": True,
    },
    "center_noise": {"kind": "center", "noise": 4, "fps": 10, "delay": 0.08, "plant_tau": 0.08},
}


def world(t, kind):
    if kind == "center":
        return (0.7, 0.3)
    if t < 1:
        return (0.0, 0.0)
    if kind == "sine":
        return (5 * math.sin(0.65 * (t - 1)), 2.5 * math.sin(0.9 * (t - 1)))
    if kind == "limit":
        return (14.0, -12.0) if t < 9 else (0.0, 0.0)
    return (6.0, -3.0)


def run(controller, scenario, seed=42):
    cfg = Settings(gain=0.1, deadband=0.001) if scenario.get("slow") else Settings()
    servo = controller(cfg)
    rng = random.Random(seed)
    step, duration = 0.005, 18.0
    position = [0.0, 0.0]
    command = [0.0, 0.0]
    pending, latest, rows = [], None, []
    next_frame = 0.0
    previous_velocity = [0.0, 0.0]
    for index in range(round(duration / step)):
        now = index * step
        truth = world(now, scenario["kind"])
        if now + 1e-10 >= next_frame:
            next_frame += 1 / scenario["fps"]
            if scenario.get("drop") and 7 <= now < 7.5:
                observation = None
            else:
                coords = []
                for k, (fov, sign, extent) in enumerate(
                    ((cfg.hfov_deg, cfg.yaw_sign, 640), (cfg.vfov_deg, cfg.pitch_sign, 480))
                ):
                    error = truth[k] - sign * position[k]
                    center = 0.5 + math.tan(math.radians(error)) / (
                        2 * math.tan(math.radians(fov / 2))
                    )
                    coords.append(
                        max(10, min(extent - 10, center * extent + rng.gauss(0, scenario["noise"])))
                    )
                x, y = coords
                observation = Detection(x - 8, y - 8, x + 8, y + 8, 640, 480, 0.95, now)
            pending.append((now + scenario["delay"], observation))
        while pending and pending[0][0] <= now + 1e-10:
            _, latest = pending.pop(0)
        if index % 10 == 0:
            measured = tuple(round(v * 10) / 10 for v in position)
            aim = servo.update(latest, now, measured, 1)
            unquantized = (aim.yaw, aim.pitch)
            command = [round(v * 10) / 10 for v in unquantized]
            velocity = list(servo.velocity)
            rows.append(
                {
                    "time": now,
                    "yaw": position[0],
                    "pitch": position[1],
                    "goal_yaw": command[0],
                    "goal_pitch": command[1],
                    "ref_yaw": unquantized[0],
                    "ref_pitch": unquantized[1],
                    "yaw_error": truth[0] - cfg.yaw_sign * position[0],
                    "pitch_error": truth[1] - cfg.pitch_sign * position[1],
                    "rate_yaw": velocity[0],
                    "rate_pitch": velocity[1],
                    "rate_jump": max(abs(a - b) for a, b in zip(velocity, previous_velocity)),
                    "centered": aim.centered,
                    "limited": aim.limited,
                }
            )
            previous_velocity = velocity
        for k in (0, 1):
            speed = max(-30, min(30, (command[k] - position[k]) / scenario["plant_tau"]))
            position[k] += speed * step
    active = [r for r in rows if r["time"] >= 1]
    reference_rates, motor_rates = [], []
    for prev, row in zip(rows, rows[1:]):
        reference_rates.append(
            [
                (row["ref_yaw"] - prev["ref_yaw"]) / 0.05,
                (row["ref_pitch"] - prev["ref_pitch"]) / 0.05,
            ]
        )
        motor_rates.append(
            [(row["yaw"] - prev["yaw"]) / 0.05, (row["pitch"] - prev["pitch"]) / 0.05]
        )

    def rms_accel(rates):
        changes = [(b - a) / 0.05 for prev, row in zip(rates, rates[1:]) for a, b in zip(prev, row)]
        return math.sqrt(sum(v * v for v in changes) / len(changes))

    metrics = {
        "tracking_rmse_deg": math.sqrt(
            sum(r["yaw_error"] ** 2 + r["pitch_error"] ** 2 for r in active) / (2 * len(active))
        ),
        "final_error_deg": math.hypot(rows[-1]["yaw_error"], rows[-1]["pitch_error"]),
        "reference_accel_rms_deg_s2": rms_accel(reference_rates),
        "simulated_motor_accel_rms_deg_s2": rms_accel(motor_rates),
        "max_reference_rate_jump_deg_s": max(r["rate_jump"] for r in rows),
        "max_command_deg": max(abs(r[key]) for r in rows for key in ("goal_yaw", "goal_pitch")),
        "limited_ticks": sum(r["limited"] for r in rows),
    }
    return metrics, rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="outputs/smooth_servo")
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "warning": "SIL with assumed first-order motor, NOT board measurements",
        "control_hz": 20,
        "wire_quantum_deg": 0.1,
        "seed": 42,
        "scenarios": {},
    }
    for name, scenario in SCENARIOS.items():
        entry = {"assumptions": scenario}
        for label, controller in (("v0.2", Baseline), ("v0.3", VisualServo)):
            metrics, rows = run(controller, scenario)
            entry[label] = metrics
            with (out / (name + "_" + label + ".csv")).open(
                "w", newline="", encoding="utf-8"
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        report["scenarios"][name] = entry
        print(name, json.dumps({k: entry[k] for k in ("v0.2", "v0.3")}))
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

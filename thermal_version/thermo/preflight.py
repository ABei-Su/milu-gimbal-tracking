"""Read-only capability inspection; does not open GPIO, motors or sensor buses."""

import argparse
import importlib
import json
from pathlib import Path
from thermo.config import load_config


def inspect(cfg, importer=importlib.import_module):
    results = []
    results.append(
        {
            "check": "vendor_protocol",
            "ok": cfg.sensor_backend != "pending_uart",
            "detail": "VENDOR_UART_PROTOCOL_REQUIRED"
            if cfg.sensor_backend == "pending_uart"
            else cfg.sensor_backend,
        }
    )
    results.append(
        {
            "check": "sensor_confirmed",
            "ok": cfg.sensor_confirmed,
            "detail": "hardware type and electrical contract",
        }
    )
    results.append(
        {
            "check": "alignment",
            "ok": cfg.alignment_confirmed,
            "detail": "fixed-distance RGB/IR calibration",
        }
    )
    results.append(
        {
            "check": "tracker_model",
            "ok": Path(cfg.tracker_model).is_file(),
            "detail": cfg.tracker_model,
        }
    )
    try:
        maix = importer("maix")
        results.append(
            {
                "check": "MixFormerV2",
                "ok": hasattr(maix.nn, "MixFormerV2"),
                "detail": "MaixCAM2 SDK",
            }
        )
        if cfg.sensor_backend == "mlx90640_i2c":
            results.append(
                {
                    "check": "MLX90640Celsius",
                    "ok": hasattr(maix.ext_dev.mlx90640, "MLX90640Celsius"),
                    "detail": "standard MLX90640 I2C (Waveshare D55)",
                }
            )
    except (ImportError, AttributeError) as exc:
        results.append({"check": "SDK", "ok": False, "detail": str(exc)})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default=str(Path(__file__).resolve().parents[1] / "thermal.json")
    )
    args = parser.parse_args()
    results = inspect(load_config(args.config))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

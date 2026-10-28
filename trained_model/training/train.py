import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["YOLO_CONFIG_DIR"] = str(ROOT / "ultralytics_settings")


def main():
    import torch
    from ultralytics import YOLO

    torch.set_num_threads(4)
    if (ROOT / "run").exists():
        raise RuntimeError("Run exists: preserve it; explicit resume required")
    model = YOLO("yolo11n.pt")
    model.train(
        data=str(ROOT / "dataset/data.yaml"),
        epochs=100,
        imgsz=640,
        batch=8,
        workers=0,
        device=0,
        seed=42,
        deterministic=True,
        amp=False,
        patience=20,
        optimizer="AdamW",
        lr0=0.001,
        freeze=0,
        project=str(ROOT),
        name="run",
        exist_ok=False,
        mosaic=0.2,
        close_mosaic=10,
        mixup=0.0,
        degrees=8,
        fliplr=0.5,
        plots=True,
    )
    best = Path(model.trainer.best)
    detector = YOLO(str(best))
    metrics = detector.val(
        data=str(ROOT / "dataset/data.yaml"),
        split="test",
        device=0,
        workers=0,
        project=str(ROOT),
        name="test_evaluation",
        exist_ok=False,
    )
    (ROOT / "metrics.json").write_text(
        json.dumps(
            {
                "weights": str(best),
                "test_metrics": metrics.results_dict,
                "limitations": "User-label agreement on grouped holdout; not independent wildlife or hardware validation",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    exported = detector.export(
        format="onnx", imgsz=(480, 640), opset=17, dynamic=False, simplify=False, device="cpu"
    )
    print("TRAINING_COMPLETE", best, exported, flush=True)


if __name__ == "__main__":
    main()

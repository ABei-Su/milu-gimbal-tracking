"""Reproducible prototype pipeline: licensed photos -> candidate boxes -> YOLO11."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil

ROOT = Path(__file__).resolve().parents[1]
(ROOT / ".cache/ultralytics").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / ".cache/ultralytics"))
os.environ.setdefault("TORCH_HOME", str(ROOT / ".cache/torch"))


def prepare():
    from ultralytics import YOLOWorld
    from PIL import Image, ImageDraw, ImageOps

    raw = ROOT / "data/milu_inaturalist"
    records = [
        json.loads(x) for x in (raw / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    model = YOLOWorld(str(ROOT / "models/yolov8s-worldv2.pt"))
    model.set_classes(["deer"])
    dataset = ROOT / "data/milu_prototype"
    # Remove only previously generated split files within this fixed dataset root.
    # Rebuilding groups after new downloads must not leave images in two splits.
    for folder in ("images", "labels"):
        base = (dataset / folder).resolve()
        if not base.is_relative_to((ROOT / "data").resolve()):
            raise ValueError("dataset path outside workspace")
        if base.exists():
            for old in base.rglob("*"):
                if old.is_file() and old.suffix in (".jpg", ".txt", ".cache"):
                    old.unlink()
    (dataset / "review").mkdir(parents=True, exist_ok=True)
    groups = sorted({r["split_group"] for r in records})
    random.Random(42).shuffle(groups)
    if len(groups) < 6:
        raise ValueError("Need at least six independent contributor groups")
    n = max(1, len(groups) // 5)
    mapping = {
        g: "test" if i < n else "val" if i < 2 * n else "train" for i, g in enumerate(groups)
    }
    labels_manifest = []
    tiles = []
    for record in records:
        path = raw / record["file"]
        normalized = dataset / "review" / (path.stem + ".jpg")
        with Image.open(path) as img:
            rgb = ImageOps.exif_transpose(img).convert("RGB")
            rgb.save(normalized)
        prediction = model.predict(str(normalized), conf=0.30, iou=0.45, device=0, verbose=False)[0]
        boxes = prediction.boxes.xywhn.cpu().tolist()
        if not boxes:
            labels_manifest.append({"id": path.stem, "status": "unlabeled-excluded", "count": 0})
            continue
        split = mapping[record["split_group"]]
        for folder in ("images", "labels"):
            (dataset / folder / split).mkdir(parents=True, exist_ok=True)
        shutil.copy2(normalized, dataset / "images" / split / normalized.name)
        label = "\n".join("0 " + " ".join(f"{v:.7f}" for v in box) for box in boxes) + "\n"
        (dataset / "labels" / split / (path.stem + ".txt")).write_text(label, encoding="utf-8")
        labels_manifest.append(
            {
                "id": path.stem,
                "status": "machine-proposal-not-human-ground-truth",
                "source": record["source"],
                "group": record["split_group"],
                "split": split,
                "count": len(boxes),
            }
        )
        annotated = Image.fromarray(prediction.plot()[..., ::-1])
        annotated.thumbnail((380, 260))
        tile = Image.new("RGB", (384, 290), "white")
        tile.paste(annotated, ((384 - annotated.width) // 2, 20))
        ImageDraw.Draw(tile).text((4, 3), path.stem + " " + split, fill="black")
        tiles.append(tile)
        print("labeled", path.stem, split, len(boxes), flush=True)
    for start in range(0, len(tiles), 12):
        sheet = Image.new("RGB", (384 * 3, 290 * 4), "#ddd")
        for i, tile in enumerate(tiles[start : start + 12]):
            sheet.paste(tile, ((i % 3) * 384, (i // 3) * 290))
        sheet.save(dataset / "review" / f"sheet_{start // 12}.jpg")
    (dataset / "annotations.json").write_text(
        json.dumps(labels_manifest, indent=2), encoding="utf-8"
    )
    (dataset / "data.yaml").write_text(
        f"path: {dataset.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: milu\n",
        encoding="utf-8",
    )
    for split in ("train", "val", "test"):
        count = len(list((dataset / "images" / split).glob("*.jpg")))
        if count == 0:
            raise ValueError("Empty split: " + split)
        print(split, count)
    print("Review all proposal sheets before treating labels as reliable.")


def train(epochs):
    from ultralytics import YOLO

    dataset = ROOT / "data/milu_prototype/data.yaml"
    if not dataset.exists():
        raise FileNotFoundError("Run --prepare first")
    model = YOLO(str(ROOT / "models/yolo11n.pt"))
    model.train(
        data=str(dataset),
        epochs=epochs,
        imgsz=640,
        batch=8,
        workers=0,
        device=0,
        seed=42,
        deterministic=True,
        amp=False,
        patience=40,
        optimizer="AdamW",
        lr0=0.0005,
        freeze=10,
        project=str(ROOT / "runs"),
        name="milu_finetuned",
        exist_ok=False,
        mosaic=0.2,
        close_mosaic=10,
        mixup=0.0,
        degrees=8,
        fliplr=0.5,
    )
    best = model.trainer.best
    final = YOLO(str(best))
    metrics = final.val(data=str(dataset), split="test", device=0, workers=0)
    summary = {
        "status": "prototype-trained-on-machine-proposals",
        "weights": str(best),
        "metrics_against_machine_proposals_only": metrics.results_dict,
        "not_claimed": "human-validated species accuracy or MaixCAM2 hardware performance",
    }
    (ROOT / "models/prototype_metrics.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    shutil.copy2(best, ROOT / "models/milu_prototype.pt")
    output = final.export(
        format="onnx",
        imgsz=(480, 640),
        opset=17,
        dynamic=False,
        simplify=False,
        device="cpu",
    )
    shutil.copy2(output, ROOT / "models/milu_prototype.onnx")
    digest = hashlib.sha256((ROOT / "models/milu_prototype.pt").read_bytes()).hexdigest()
    print("Prototype weights SHA256", digest)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--epochs", type=int, default=60)
    args = parser.parse_args()
    if not (args.prepare or args.train):
        parser.error("choose --prepare and/or --train")
    if not 1 <= args.epochs <= 300:
        parser.error("epochs must be 1..300")
    if args.prepare:
        prepare()
    if args.train:
        train(args.epochs)


if __name__ == "__main__":
    main()

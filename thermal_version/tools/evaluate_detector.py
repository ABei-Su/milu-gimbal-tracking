"""One inference per image; threshold sweep against machine proposals, not human GT."""

import argparse
import json
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("YOLO_CONFIG_DIR", str(ROOT / ".cache/ultralytics"))


def corners(box):
    x, y, w, h = box
    return x - w / 2, y - h / 2, x + w / 2, y + h / 2


def iou(a, b):
    a, b = corners(a), corners(b)
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - overlap
    return overlap / union if union else 0


def collect(model, dataset, split, device):
    rows = []
    images = sorted((dataset / "images" / split).glob("*.jpg"))
    if not images:
        raise ValueError("empty dataset split: " + split)
    for path in images:
        label = dataset / "labels" / split / (path.stem + ".txt")
        expected = [list(map(float, line.split()[1:])) for line in label.read_text().splitlines()]
        result = model.predict(
            str(path), conf=0.25, iou=0.45, max_det=300, device=device, verbose=False
        )[0]
        boxes = result.boxes.xywhn.cpu().tolist()
        scores = result.boxes.conf.cpu().tolist()
        rows.append(
            {
                "id": path.stem,
                "expected": expected,
                "predictions": sorted(zip(scores, boxes), key=lambda item: -item[0]),
            }
        )
    return rows


def score_rows(rows, split, threshold):
    if not 0.25 <= threshold < 1:
        raise ValueError("threshold below cache floor or outside range")
    tp = fp = fn = 0
    for row in rows:
        matched = set()
        for confidence, prediction in row["predictions"]:
            if confidence < threshold:
                continue
            candidates = [
                (iou(prediction, box), j)
                for j, box in enumerate(row["expected"])
                if j not in matched
            ]
            best = max(candidates, default=(0, -1))
            if best[0] >= 0.5:
                tp += 1
                matched.add(best[1])
            else:
                fp += 1
        fn += len(row["expected"]) - len(matched)
    precision, recall = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return dict(
        split=split,
        confidence=threshold,
        images=len(rows),
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=2 * precision * recall / max(precision + recall, 1e-9),
    )


def main():
    from ultralytics import YOLO

    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", default=str(ROOT / "models/milu_prototype.pt"))
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/milu_prototype")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "outputs/recognition/threshold_report.json"
    )
    parser.add_argument("--device", default="0")
    args = parser.parse_args()
    model = YOLO(args.weights)
    started = time.perf_counter()
    rows = collect(model, args.dataset, "val", args.device)
    validation = [score_rows(rows, "val", v) for v in (0.25, 0.4, 0.55, 0.65)]
    best = max(validation, key=lambda result: result["f1"])
    test = collect(model, args.dataset, "test", args.device)
    report = {
        "annotation_status": "machine proposals; previously used development split; not species accuracy",
        "validation": validation,
        "suggested_confidence": best["confidence"],
        "development_test": score_rows(test, "test", best["confidence"]),
        "strong_threshold_test": score_rows(test, "test", 0.65),
        "continuation_threshold_test": score_rows(test, "test", 0.4),
        "inference_images": len(rows) + len(test),
        "previous_sweep_inference_images": len(rows) * 4 + len(test),
        "wall_seconds": time.perf_counter() - started,
        "scope": "PC floating-point model; NMS 0.45; min confidence 0.25; max_det 300; no MaixCAM2 timing",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

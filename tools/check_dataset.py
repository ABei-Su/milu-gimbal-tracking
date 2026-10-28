"""Audit dataset boundaries, annotation ranges and grouped split isolation."""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    dataset = ROOT / "data/milu_prototype"
    records = json.loads((dataset / "annotations.json").read_text(encoding="utf-8"))
    groups, stems = {}, {}
    count = 0
    for row in records:
        if "split" not in row:
            continue
        group, split, stem = row["group"], row["split"], row["id"]
        if group in groups and groups[group] != split:
            raise ValueError("contributor leaked across splits")
        groups[group] = split
        if stem in stems:
            raise ValueError("duplicate image id")
        stems[stem] = split
        label = dataset / "labels" / split / (stem + ".txt")
        for line in label.read_text(encoding="utf-8").splitlines():
            cls, x, y, w, h = map(float, line.split())
            if cls != 0 or not all(math.isfinite(v) for v in (x, y, w, h)):
                raise ValueError("invalid label")
            if not (
                0 < w <= 1
                and 0 < h <= 1
                and -1e-6 <= x - w / 2 <= x + w / 2 <= 1 + 1e-6
                and -1e-6 <= y - h / 2 <= y + h / 2 <= 1 + 1e-6
            ):
                raise ValueError("box out of range")
            count += 1
    seen = {}
    for split in ("train", "val", "test"):
        for image in (dataset / "images" / split).glob("*.jpg"):
            if image.stem in seen:
                raise ValueError("image present in multiple splits")
            seen[image.stem] = split
    if seen != stems:
        raise ValueError("disk files do not match annotation manifest")
    print(
        "PASS", len(stems), "images,", count, "boxes,", len(groups), "isolated contributor groups"
    )


if __name__ == "__main__":
    main()

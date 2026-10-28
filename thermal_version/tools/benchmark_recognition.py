"""Deterministic score-dip replay, not a real-world recognition accuracy claim."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def replay(cls):
    from milu.settings import Settings
    from milu.tracking import Detection

    selector = cls(Settings())
    tracked = weak = 0
    for i in range(100):
        t = i * 0.05
        score = 0.9 if i % 5 in (0, 4) else 0.45
        x = 300 + (i % 5)
        d = Detection(x, 220, x + 40, 260, 640, 480, score, t)
        selected, ambiguous = selector.select([d], t, t)
        tracked += selected is not None
        if selected is not None and score < 0.65:
            assert ambiguous
            weak += 1
    return dict(frames=100, tracked_frames=tracked, weak_continuations=weak)


def main():
    from milu.targeting import TargetSelector
    from tools.selector_v030 import TargetSelector as Previous

    result = {
        "scope": "synthetic confidence-dip replay; no image/model or board timing",
        "before": replay(Previous),
        "after": replay(TargetSelector),
    }
    path = ROOT / "outputs/recognition/continuity.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

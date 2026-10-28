"""Numerically verify raw-head ABI by decoding it back to exported YOLO output."""

import json
from pathlib import Path
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[1]


def main():
    original = ort.InferenceSession(
        str(ROOT / "models/milu_prototype.onnx"), providers=["CPUExecutionProvider"]
    )
    trimmed = ort.InferenceSession(
        str(ROOT / "outputs/maixcam2_convert/export.onnx"), providers=["CPUExecutionProvider"]
    )
    x = np.random.default_rng(42).random((1, 3, 480, 640), dtype=np.float32)
    expected = original.run(None, {"images": x})[0]
    decoded = []
    for raw, stride in zip(trimmed.run(None, {"images": x}), (8, 16, 32)):
        _, channels, h, w = raw.shape
        assert channels == 65
        box = raw[:, :64].reshape(1, 4, 16, h * w)
        box = np.exp(box - box.max(axis=2, keepdims=True))
        distance = (box / box.sum(axis=2, keepdims=True) * np.arange(16)[None, None, :, None]).sum(
            axis=2
        )
        yy, xx = np.meshgrid(np.arange(h) + 0.5, np.arange(w) + 0.5, indexing="ij")
        anchor = np.stack((xx.ravel(), yy.ravel()))[None]
        low, high = anchor - distance[:, :2], anchor + distance[:, 2:]
        xywh = np.concatenate(((low + high) / 2, high - low), axis=1) * stride
        cls = 1 / (1 + np.exp(-raw[:, 64:].reshape(1, 1, h * w)))
        decoded.append(np.concatenate((xywh, cls), axis=1))
    actual = np.concatenate(decoded, axis=2)
    np.testing.assert_allclose(actual, expected, atol=0.002, rtol=1e-5)
    report = {
        "check": "raw-head DFL decode equals original ONNX",
        "input": [1, 3, 480, 640],
        "max_absolute_error": float(np.max(np.abs(actual - expected))),
        "passed": True,
    }
    (ROOT / "models/conversion_check.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(report)


if __name__ == "__main__":
    main()

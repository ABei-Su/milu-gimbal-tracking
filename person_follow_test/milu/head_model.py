"""Select real face models for MaixCAM2; never relabel person detections."""

import configparser
from pathlib import Path


def resolve_face_model(path, directory="/root/models"):
    if str(path) == "auto:face":
        available = sorted(Path(directory).glob("*.mud"))
        for candidate in available:
            try:
                return resolve_face_model(candidate)
            except (ValueError, FileNotFoundError, configparser.Error):
                continue
        names = ", ".join(p.name for p in available)
        raise FileNotFoundError(
            "FACE_MODEL_REQUIRED: MaixCAM2 AX face model missing. "
            f"Available MUD files: {names or '(none)'}. Do not use MaixCAM cvimodel."
        )
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"FACE_MODEL_REQUIRED: {path}")
    cfg = configparser.ConfigParser()
    cfg.read(path, encoding="utf-8")
    if cfg.get("basic", "type", fallback="") != "axmodel":
        raise ValueError("Face model requires MaixCAM2 axmodel")
    kind = cfg.get("extra", "model_type", fallback="")
    labels = [s.strip() for s in cfg.get("extra", "labels", fallback="").split(",")]
    if kind not in ("yolov8", "yolo11", "retinaface", "face_detector"):
        raise ValueError("Unsupported face decoder")
    if kind.startswith("yolo") and "face" not in labels:
        raise ValueError("A real trained face class is required")
    keys = [k for k in ("model_npu", "model_vnpu") if cfg.has_option("basic", k)]
    if not keys and cfg.has_option("basic", "model"):
        keys = ["model"]
    if not keys:
        raise ValueError("Missing AX weight paths")
    for key in keys:
        weight = (path.parent / cfg.get("basic", key)).resolve()
        if not weight.is_relative_to(path.parent) or not weight.is_file():
            raise FileNotFoundError(f"Missing/local-only face weight: {weight}")
    return str(path), kind


def make_face_detector(nn, path):
    path, kind = resolve_face_model(path)
    classes = {
        "yolov8": "YOLOv8",
        "yolo11": "YOLO11",
        "retinaface": "Retinaface",
        "face_detector": "FaceDetector",
    }
    detector = getattr(nn, classes[kind])(model=path, dual_buff=False)
    class_id = list(detector.labels).index("face") if kind.startswith("yolo") else None
    return detector, class_id

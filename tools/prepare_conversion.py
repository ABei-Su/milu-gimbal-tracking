"""Prepare verified YOLO11 output graph and Pulsar2 configs for MaixCAM2."""

import argparse
import configparser
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]
NODES = [f"/milu/head{i}" for i in range(3)]


def main():
    import onnx

    parser = argparse.ArgumentParser()
    parser.add_argument("--onnx", default=str(ROOT / "models/milu_prototype.onnx"))
    args = parser.parse_args()
    model = onnx.load(args.onnx)
    onnx.checker.check_model(model)
    # Ultralytics 8.4 flattens boxes/classes separately. Rebuild the older
    # per-stride raw head ABI used by MaixPy: [DFL box logits (64), class logits].
    model = onnx.shape_inference.infer_shapes(model)
    shapes = {
        v.name: [d.dim_value for d in v.type.tensor_type.shape.dim] for v in model.graph.value_info
    }
    for i, (h, w) in enumerate(((60, 80), (30, 40), (15, 20))):
        box = f"/model.23/cv2.{i}/cv2.{i}.2/Conv_output_0"
        cls = f"/model.23/cv3.{i}/cv3.{i}.2/Conv_output_0"
        if shapes.get(box) != [1, 64, h, w] or shapes.get(cls) != [1, 1, h, w]:
            raise ValueError("YOLO11 raw head shape changed; inspect the export")
        model.graph.node.append(
            onnx.helper.make_node("Concat", [box, cls], [NODES[i]], axis=1, name=f"MiluHead{i}")
        )
        model.graph.output.append(
            onnx.helper.make_tensor_value_info(NODES[i], onnx.TensorProto.FLOAT, [1, 65, h, w])
        )
    onnx.checker.check_model(model)
    out = ROOT / "outputs/maixcam2_convert"
    (out / "config").mkdir(parents=True, exist_ok=True)
    (out / "datasets").mkdir(exist_ok=True)
    onnx.save(model, out / "with_heads.onnx")
    onnx.utils.extract_model(
        str(out / "with_heads.onnx"), str(out / "export.onnx"), ["images"], NODES
    )
    onnx.checker.check_model(onnx.load(out / "export.onnx"))
    # Use only training photos for quantization, never held-out test images.
    images = sorted((ROOT / "data/milu_prototype/images/train").glob("*.jpg"))[:64]
    if not images:
        raise ValueError("No calibration images")
    with tarfile.open(out / "datasets/train.tar", "w") as archive:
        for image in images:
            archive.add(image, arcname=image.name)
    config = {
        "model_type": "ONNX",
        "npu_mode": "NPU2",
        "quant": {
            "input_configs": [
                {
                    "tensor_name": "images",
                    "calibration_dataset": "datasets/train.tar",
                    "calibration_size": len(images),
                    "calibration_mean": [0, 0, 0],
                    "calibration_std": [255, 255, 255],
                }
            ],
            "calibration_method": "MinMax",
            "precision_analysis": True,
        },
        "input_processors": [
            {
                "tensor_name": "images",
                "tensor_format": "RGB",
                "tensor_layout": "NCHW",
                "src_format": "RGB",
                "src_dtype": "U8",
                "src_layout": "NHWC",
                "csc_mode": "NoCSC",
            }
        ],
        "output_processors": [{"tensor_name": name, "dst_perm": [0, 2, 3, 1]} for name in NODES],
        "compiler": {
            "check": 3,
            "check_mode": "CheckOutput",
            "check_cosine_simularity": 0.9,
        },
    }
    for mode, filename in (("NPU2", "npu"), ("NPU1", "vnpu")):
        config["npu_mode"] = mode
        (out / "config" / (filename + ".json")).write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )
    mud = configparser.ConfigParser()
    mud["basic"] = {
        "type": "axmodel",
        "model_npu": "milu_npu.axmodel",
        "model_vnpu": "milu_vnpu.axmodel",
    }
    mud["extra"] = {
        "model_type": "yolo11",
        "type": "detector",
        "input_type": "rgb",
        "labels": "milu",
        "input_cache": "true",
        "output_cache": "true",
        "input_cache_flush": "false",
        "output_cache_inval": "true",
        "mean": "0,0,0",
        "scale": "0.00392156862745098,0.00392156862745098,0.00392156862745098",
    }
    with (out / "milu.mud").open("w", encoding="utf-8") as stream:
        mud.write(stream)
    shutil.copy2(ROOT / "deploy/convert.sh", out / "convert.sh")
    print(
        "Prepared",
        out,
        "with",
        len(images),
        "calibration images. NPU binaries require Pulsar2.",
    )


if __name__ == "__main__":
    main()

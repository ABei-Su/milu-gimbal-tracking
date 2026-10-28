"""Create a deployable source+model bundle with an explicit file allowlist."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from milu.maixcam2 import verify_model

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    files = [
        ROOT / name
        for name in (
            "main.py",
            "base_main.py",
            "thermal_main.py",
            "config.json",
            "thermal.json",
            "thermal_gimbal.json",
            "app.yaml",
            "README.md",
            "ARCHITECTURE.md",
            "CHANGELOG.md",
        )
    ]
    files += sorted((ROOT / "thermo").glob("*.py"))
    files += sorted((ROOT / "milu").glob("*.py")) + sorted((ROOT / "docs").rglob("*.md"))
    if not args.source_only:
        verify_model(ROOT / "models/milu.mud")
        files += [
            ROOT / "models" / name for name in ("milu.mud", "milu_npu.axmodel", "milu_vnpu.axmodel")
        ]
    files += sorted((ROOT / "models").glob("*.json"))
    files += sorted((ROOT / "models").glob("*.jsonl"))
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    name = "milu_thermal_sources.zip" if args.source_only else "milu_thermal_maixcam2.zip"
    manifest = {
        str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
    }
    with zipfile.ZipFile(output / name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for p in files:
            archive.write(p, p.relative_to(ROOT))
        archive.writestr("SHA256.json", json.dumps(manifest, indent=2))
    print(output / name)


if __name__ == "__main__":
    main()

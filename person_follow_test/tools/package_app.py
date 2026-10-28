"""Package the app; official model weights remain on the device."""

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [
        ROOT / name
        for name in (
            "main.py",
            "config.json",
            "app.yaml",
            "README.md",
            "CHANGELOG.md",
            "ARCHITECTURE.md",
        )
    ]
    files += sorted((ROOT / "milu").glob("*.py"))
    files += sorted((ROOT / "docs").rglob("*.md"))
    output = ROOT / "dist/person_follow_maixcam2.zip"
    output.parent.mkdir(exist_ok=True)
    manifest = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
    }
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for p in files:
            archive.write(p, p.relative_to(ROOT))
        archive.writestr("SHA256.json", json.dumps(manifest, indent=2))
    print(output)
    print("Requires compatible MaixCAM2 AX face model on device; weights not bundled.")


if __name__ == "__main__":
    main()

"""Create six attributed A4 print pages from existing licensed local photos."""

import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
IDS = ("118649753", "136591842", "189972375", "248946166", "1960210", "124175926")


def main():
    from PIL import Image
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    raw = ROOT / "data/milu_inaturalist"
    records = {
        str(d["observation_id"]): d
        for d in (
            json.loads(line)
            for line in (raw / "manifest.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    annotations = json.loads(
        (ROOT / "data/milu_prototype/annotations.json").read_text(encoding="utf-8")
    )
    splits = {item["id"]: item.get("split", "excluded") for item in annotations}
    output = ROOT / "output/pdf"
    photos = output / "milu_print_photos"
    photos.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    pdf = canvas.Canvas(str(output / "milu_A4_print_targets.pdf"), pagesize=landscape(A4))
    pdf.setTitle("Milu A4 print targets - six attributed research photos")
    width, height = landscape(A4)
    manifest = []
    for index, identifier in enumerate(IDS, 1):
        record = records[identifier]
        path = raw / record["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("photo hash mismatch: " + identifier)
        if record["license"] not in ("cc0", "cc-by", "cc-by-nc"):
            raise ValueError("unreviewed redistribution license")
        destination = photos / (f"{index:02d}_" + identifier + path.suffix.lower())
        shutil.copy2(path, destination)
        manifest.append(dict(record, print_file=destination.name, split=splits[identifier]))
        pdf.setFont("STSong-Light", 18)
        pdf.drawString(36, height - 35, f"麋鹿打印测试图 {index:02d} / 06")
        pdf.setFont("Helvetica", 9)
        pdf.drawRightString(width - 36, height - 32, "A4 LANDSCAPE | PRINT AT 100%")
        with Image.open(path) as im:
            scale = min((width - 72) / im.width, (height - 135) / im.height)
            w, h = im.width * scale, im.height * scale
        pdf.drawImage(str(path), (width - w) / 2, 80 + (height - 135 - h) / 2, width=w, height=h)
        pdf.setFont("Helvetica", 8)
        pdf.drawString(36, 60, record["attribution"])
        pdf.drawString(36, 47, record["source"])
        license_url = (
            "https://creativecommons.org/publicdomain/zero/1.0/"
            if record["license"] == "cc0"
            else "https://creativecommons.org/licenses/"
            + record["license"].removeprefix("cc-")
            + "/4.0/"
        )
        pdf.drawString(
            36, 34, license_url + " | Original image, scaled only. Development-test image."
        )
        pdf.setFont("STSong-Light", 9)
        pdf.drawString(
            36,
            19,
            "非商业研究联调用图；来自已有开发测试集，不作为独立准确率验收。纸张不能验证鹿眼真实温度。",
        )
        pdf.showPage()
    pdf.save()
    (photos / "sources.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(output / "milu_A4_print_targets.pdf")


if __name__ == "__main__":
    main()

"""Read vendor PDFs/archive source without changing or executing them."""

from pathlib import Path
import re
import zipfile

from pypdf import PdfReader


def main():
    root = Path(__file__).resolve().parents[1]
    source = root / "WHEELTEC F32C无刷电机无刷云台附送资料"
    out = root / "tmp" / "vendor_audit"
    out.mkdir(parents=True, exist_ok=True)
    texts = []
    for path in sorted(source.rglob("*.pdf")):
        for index, page in enumerate(PdfReader(path).pages):
            text = page.extract_text() or ""
            title = f"{path.relative_to(source)} PAGE {index + 1}"
            texts.append(title + "\n" + text)
            if re.search("限位|逆时针|顺时针|转动范围|旋转范围|正方向|零位|零点|360|180", text):
                print(title)
                for line in text.splitlines():
                    if re.search(
                        "限位|逆时针|顺时针|转动范围|旋转范围|正方向|零位|零点|360|180",
                        line,
                    ):
                        print(line)
    (out / "pdf_text.txt").write_text("\n\n".join(texts), encoding="utf-8")
    archive_text = []
    for path in sorted(source.rglob("*.zip")):
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith((".c", ".h", ".py")):
                    continue
                if any(
                    part in name.lower()
                    for part in (
                        "library/",
                        "libraries/",
                        "cmsis/",
                        "drivers/",
                        "freertos/",
                    )
                ):
                    continue
                data = archive.read(name)
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    text = data.decode("gb18030", errors="replace")
                text = text.replace("\r\r\n", "\n")
                archive_text.append(f"{path.name} :: {name}\n{text}")
                if re.search("限位|逆时针|顺时针|yaw|pitch|Yaw|Pitch|Angle_Limit", text):
                    print("SOURCE", path.name, name)
                    for line in text.splitlines():
                        if re.search("限位|逆时针|顺时针|yaw|pitch|Yaw|Pitch|Angle_Limit", line):
                            print(line[:200])
    (out / "archive_source.txt").write_text("\n\n".join(archive_text), encoding="utf-8")
    print("Audit output", out)


if __name__ == "__main__":
    main()

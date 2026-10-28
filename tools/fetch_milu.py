"""Download licensed Elaphurus davidianus photos with attribution records."""

import argparse
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LICENSES = {"cc0", "cc-by", "cc-by-sa"}


def fetch(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "MiluPrototype/0.2 licensed dataset preparation"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read(15000001)
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2**attempt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument(
        "--allow-noncommercial",
        action="store_true",
        help="Include CC-BY-NC/NC-SA for noncommercial research only",
    )
    args = parser.parse_args()
    if args.allow_noncommercial:
        LICENSES.update({"cc-by-nc", "cc-by-nc-sa"})
    if not 1 <= args.limit <= 500:
        parser.error("limit must be 1..500")
    out = ROOT / "data/milu_inaturalist"
    (out / "images").mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.jsonl"
    records = (
        [json.loads(x) for x in manifest.read_text(encoding="utf-8").splitlines()]
        if manifest.exists()
        else []
    )
    existing = {r["observation_id"] for r in records}
    hashes = {r["sha256"] for r in records}
    for page in range(1, 11):
        query = urllib.parse.urlencode(
            {
                "taxon_id": 42230,
                "photos": "true",
                "photo_license": ",".join(sorted(LICENSES)),
                "per_page": 100,
                "page": page,
                "order_by": "id",
                "order": "asc",
            }
        )
        result = json.loads(fetch("https://api.inaturalist.org/v1/observations?" + query))
        print("page", page, "available", result.get("total_results"), flush=True)
        if not result["results"]:
            break
        for item in result["results"]:
            if len(records) >= args.limit:
                break
            if item["id"] in existing or item.get("taxon", {}).get("id") != 42230:
                continue
            for photo in item["photos"]:
                if photo.get("license_code") not in LICENSES:
                    continue
                url = photo["url"].replace("/square.", "/large.")
                try:
                    data = fetch(url)
                except OSError as exc:
                    print("download failed", item["id"], str(exc), flush=True)
                    continue
                digest = hashlib.sha256(data).hexdigest()
                if digest in hashes or len(data) > 15000000:
                    continue
                suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
                if suffix not in (".jpg", ".jpeg", ".png"):
                    continue
                name = str(item["id"]) + suffix
                (out / "images" / name).write_bytes(data)
                record = {
                    "observation_id": item["id"],
                    "photo_id": photo["id"],
                    "file": "images/" + name,
                    "taxon_id": 42230,
                    "species": "Elaphurus davidianus",
                    "license": photo["license_code"],
                    "attribution": photo.get("attribution", ""),
                    "source": item["uri"],
                    "image_url": url,
                    "sha256": digest,
                    "annotation": "unannotated",
                    "quality_grade": item.get("quality_grade"),
                    "split_group": str(item.get("user", {}).get("id", item["id"])),
                }
                records.append(record)
                with manifest.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                existing.add(item["id"])
                hashes.add(digest)
                print("downloaded", len(records), name, photo["license_code"], flush=True)
                time.sleep(0.25)
                break
        if len(records) >= args.limit:
            break
        time.sleep(1)
    print(
        "Downloaded",
        len(records),
        "species photos. Bounding boxes still require annotation.",
    )


if __name__ == "__main__":
    main()

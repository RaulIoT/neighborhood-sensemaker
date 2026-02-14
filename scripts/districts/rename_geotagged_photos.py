#!/usr/bin/env python3
"""
Rename geotagged photos and export a CSV report.

Example:
python3 rename_geotagged_photos.py \
  --input-dir "Leppävaara_photos" \
  --prefix "Leppävaara" \
  --csv-out "Data/leppavaara_photo_index.csv"
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import time
import uuid
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from PIL import ExifTags, Image


GPS_INFO_TAG = next(k for k, v in ExifTags.TAGS.items() if v == "GPSInfo")
DATETIME_ORIGINAL_TAG = next(
    k for k, v in ExifTags.TAGS.items() if v == "DateTimeOriginal"
)
RENAMED_PATTERN = re.compile(r".*_(\d+)(?:-(\d+))?_(.+)$")


@dataclass
class PhotoRecord:
    path: Path
    original_name: str
    capture_dt: datetime | None
    lat: float
    lon: float
    address: str
    place_slug: str
    location_group: int = -1
    location_seq: int = -1
    duplicate_idx: int = 0
    new_name: str = ""


def dms_to_decimal(dms: tuple[Any, Any, Any], ref: str) -> float:
    deg = float(dms[0])
    minute = float(dms[1])
    sec = float(dms[2])
    value = deg + minute / 60.0 + sec / 3600.0
    if ref in {"S", "W"}:
        value *= -1
    return value


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius * c


def slugify_place(text: str) -> str:
    clean = unicodedata.normalize("NFC", text.strip().lower())
    clean = re.sub(r"\s+", "_", clean)
    clean = re.sub(r"[^\wäöå]+", "_", clean, flags=re.IGNORECASE)
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or "unknown_place"


def parse_capture_datetime(exif_raw: dict[int, Any]) -> datetime | None:
    value = exif_raw.get(DATETIME_ORIGINAL_TAG)
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def extract_gps(exif_raw: Any) -> tuple[float, float] | None:
    if not exif_raw:
        return None
    try:
        gps_ifd = exif_raw.get_ifd(GPS_INFO_TAG)
    except Exception:
        gps_ifd = None
    if not gps_ifd:
        return None
    gps_data = {
        ExifTags.GPSTAGS.get(tag_id, tag_id): val for tag_id, val in gps_ifd.items()
    }
    lat_dms = gps_data.get("GPSLatitude")
    lat_ref = gps_data.get("GPSLatitudeRef")
    lon_dms = gps_data.get("GPSLongitude")
    lon_ref = gps_data.get("GPSLongitudeRef")
    if not (lat_dms and lat_ref and lon_dms and lon_ref):
        return None
    lat = dms_to_decimal(lat_dms, str(lat_ref))
    lon = dms_to_decimal(lon_dms, str(lon_ref))
    return lat, lon


def reverse_geocode(lat: float, lon: float, user_agent: str, timeout: int) -> tuple[str, str]:
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": lat, "lon": lon, "format": "jsonv2", "addressdetails": 1}
    headers = {"User-Agent": user_agent}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return "", "unknown_place"

    address = data.get("display_name", "")
    addr = data.get("address", {})
    candidates = [
        addr.get("park"),
        addr.get("road"),
        addr.get("pedestrian"),
        addr.get("suburb"),
        addr.get("neighbourhood"),
        addr.get("city_district"),
        addr.get("city"),
        data.get("name"),
    ]
    place = next((c for c in candidates if c), "") or "unknown_place"
    return address, slugify_place(place)


def ensure_unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    i = 1
    while True:
        candidate = target.with_name(f"{target.stem}_dup{i}{target.suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def parse_existing_seq_and_dup(filename: str) -> tuple[int, int] | None:
    stem = Path(filename).stem
    match = RENAMED_PATTERN.match(stem)
    if not match:
        return None
    seq = int(match.group(1))
    dup = int(match.group(2)) if match.group(2) else 0
    return seq, dup


def build_records(input_dir: Path) -> list[PhotoRecord]:
    files = sorted(
        [p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg"}]
    )
    records: list[PhotoRecord] = []
    for photo in files:
        with Image.open(photo) as img:
            exif_raw = img.getexif() or {}
            capture_dt = parse_capture_datetime(exif_raw)
        gps = extract_gps(exif_raw)
        if gps is None:
            continue
        lat, lon = gps
        records.append(
            PhotoRecord(
                path=photo,
                original_name=photo.name,
                capture_dt=capture_dt,
                lat=lat,
                lon=lon,
                address="",
                place_slug="unknown_place",
            )
        )
    records.sort(key=lambda r: (r.capture_dt or datetime.max, r.original_name))
    return records


def assign_location_groups(records: list[PhotoRecord], same_spot_m: float) -> None:
    groups: list[tuple[float, float]] = []

    for rec in records:
        matched_idx = None
        for i, (glat, glon) in enumerate(groups):
            if haversine_m(rec.lat, rec.lon, glat, glon) <= same_spot_m:
                matched_idx = i
                break
        if matched_idx is None:
            groups.append((rec.lat, rec.lon))
            matched_idx = len(groups) - 1
        rec.location_group = matched_idx

    seq_map = {group_idx: i + 1 for i, group_idx in enumerate(sorted(set(r.location_group for r in records)))}
    for rec in records:
        rec.location_seq = seq_map[rec.location_group]

    by_group: dict[int, list[PhotoRecord]] = defaultdict(list)
    for rec in records:
        by_group[rec.location_group].append(rec)

    for group_id, grouped in by_group.items():
        location_seq = seq_map[group_id]

        def within_group_sort_key(item: PhotoRecord) -> tuple[Any, ...]:
            if item.capture_dt is not None:
                return (0, item.capture_dt, item.original_name)
            parsed = parse_existing_seq_and_dup(item.original_name)
            if parsed and parsed[0] == location_seq:
                return (1, parsed[1], item.original_name)
            return (2, item.original_name)

        grouped.sort(key=within_group_sort_key)
        for i, rec in enumerate(grouped):
            rec.duplicate_idx = i


def geocode_records_by_group(
    records: list[PhotoRecord],
    user_agent: str,
    timeout: int,
    geocode_delay_s: float,
) -> int:
    by_group: dict[int, list[PhotoRecord]] = defaultdict(list)
    for rec in records:
        by_group[rec.location_group].append(rec)

    success_count = 0
    for group_id in sorted(by_group):
        ref = by_group[group_id][0]
        address, place_slug = reverse_geocode(ref.lat, ref.lon, user_agent, timeout)
        if place_slug != "unknown_place":
            success_count += 1
        for rec in by_group[group_id]:
            rec.address = address
            rec.place_slug = place_slug
        if geocode_delay_s > 0:
            time.sleep(geocode_delay_s)
    return success_count


def build_new_filename(prefix: str, rec: PhotoRecord, digits: int, ext: str) -> str:
    base = f"{prefix}_{rec.location_seq:0{digits}d}"
    if rec.duplicate_idx > 0:
        base = f"{base}-{rec.duplicate_idx}"
    return f"{base}_{rec.place_slug}{ext}"


def rename_photos(
    records: list[PhotoRecord], output_dir: Path, prefix: str, digits: int, dry_run: bool
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    source_in_output_dir = {
        rec.path.name
        for rec in records
        if rec.path.parent.resolve() == output_dir.resolve()
    }
    existing_files = {p.name for p in output_dir.iterdir() if p.is_file()}
    reserved_names = (
        existing_files - source_in_output_dir
        if source_in_output_dir
        else existing_files
    )
    planned_names: set[str] = set()

    for rec in records:
        ext = rec.path.suffix.lower()
        candidate = build_new_filename(prefix, rec, digits, ext)
        candidate_path = output_dir / candidate
        if (
            candidate in planned_names
            or (candidate in reserved_names and candidate_path.resolve() != rec.path.resolve())
        ):
            base_stem = candidate_path.stem
            i = 1
            while True:
                next_name = f"{base_stem}_dup{i}{candidate_path.suffix}"
                next_path = output_dir / next_name
                if (
                    next_name not in planned_names
                    and (
                        next_name not in reserved_names
                        or next_path.resolve() == rec.path.resolve()
                    )
                ):
                    candidate = next_name
                    break
                i += 1
        rec.new_name = candidate
        planned_names.add(candidate)

    if dry_run:
        return

    in_place = all(rec.path.parent.resolve() == output_dir.resolve() for rec in records)

    if in_place:
        for rec in records:
            temp_name = f".tmp_ren_{uuid.uuid4().hex}{rec.path.suffix.lower()}"
            temp_path = ensure_unique_path(output_dir / temp_name)
            rec.path.rename(temp_path)
            rec.path = temp_path
        for rec in records:
            final_path = output_dir / rec.new_name
            rec.path.rename(final_path)
            rec.path = final_path
        return

    for rec in records:
        final_path = output_dir / rec.new_name
        rec.path.rename(final_path)
        rec.path = final_path


def write_csv(records: list[PhotoRecord], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "original_name",
                "new_name",
                "latitude",
                "longitude",
                "address",
                "place_slug",
                "location_group_id",
                "location_sequence",
                "duplicate_index",
                "capture_datetime",
            ],
        )
        writer.writeheader()
        for rec in records:
            writer.writerow(
                {
                    "original_name": rec.original_name,
                    "new_name": rec.new_name,
                    "latitude": f"{rec.lat:.8f}",
                    "longitude": f"{rec.lon:.8f}",
                    "address": rec.address,
                    "place_slug": rec.place_slug,
                    "location_group_id": rec.location_group,
                    "location_sequence": rec.location_seq,
                    "duplicate_index": rec.duplicate_idx,
                    "capture_datetime": rec.capture_dt.isoformat(sep=" ") if rec.capture_dt else "",
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename geotagged photos by location and export a CSV index."
    )
    parser.add_argument(
        "--input-dir",
        default="Leppävaara_photos",
        type=Path,
        help="Folder that contains JPG/JPEG photos with GPS EXIF metadata.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Where to write renamed photos. Default: rename in place (same as input).",
    )
    parser.add_argument(
        "--prefix",
        default="Leppävaara",
        help='Filename prefix, e.g. "Leppävaara".',
    )
    parser.add_argument(
        "--place-name",
        default=None,
        help='Force place suffix (all photos unless --place-name-first-n is set), e.g. "hatsinanpuisto".',
    )
    parser.add_argument(
        "--place-name-first-n",
        type=int,
        default=0,
        help="If > 0, force --place-name only for first N photos (sorted by capture time/name).",
    )
    parser.add_argument(
        "--digits",
        type=int,
        default=2,
        help="Zero-padding for location sequence numbers.",
    )
    parser.add_argument(
        "--same-spot-m",
        type=float,
        default=12.0,
        help="Distance threshold in meters to treat photos as same location.",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=Path("Data/leppavaara_photo_index.csv"),
        help="CSV output path.",
    )
    parser.add_argument(
        "--no-geocode",
        action="store_true",
        help="Skip reverse geocoding (address/place will be empty/unknown).",
    )
    parser.add_argument(
        "--geocode-delay-s",
        type=float,
        default=1.0,
        help="Delay between reverse geocode requests to avoid rate limiting.",
    )
    parser.add_argument(
        "--geocode-timeout-s",
        type=int,
        default=20,
        help="HTTP timeout in seconds for reverse geocoding requests.",
    )
    parser.add_argument(
        "--user-agent",
        default="urban-experience-photo-renamer/1.0 (contact: local-script)",
        help="User-Agent string for Nominatim requests.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute names + CSV only, do not rename files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir or input_dir
    do_geocode = not args.no_geocode

    if not input_dir.exists():
        raise SystemExit(f"Input directory does not exist: {input_dir}")
    if args.output_dir and input_dir.resolve() == output_dir.resolve() and not args.dry_run:
        pass

    records = build_records(input_dir=input_dir)
    if not records:
        raise SystemExit("No JPG/JPEG files with GPS EXIF metadata found.")

    assign_location_groups(records, same_spot_m=args.same_spot_m)

    geocode_success_groups = 0
    if do_geocode:
        geocode_success_groups = geocode_records_by_group(
            records=records,
            user_agent=args.user_agent,
            timeout=args.geocode_timeout_s,
            geocode_delay_s=args.geocode_delay_s,
        )

    if args.place_name:
        forced_slug = slugify_place(args.place_name)
        if args.place_name_first_n > 0:
            n = min(args.place_name_first_n, len(records))
            for rec in records[:n]:
                rec.place_slug = forced_slug
        else:
            for rec in records:
                rec.place_slug = forced_slug

    rename_photos(
        records=records,
        output_dir=output_dir,
        prefix=args.prefix,
        digits=args.digits,
        dry_run=args.dry_run,
    )
    write_csv(records, args.csv_out)

    print(f"Processed photos: {len(records)}")
    print(f"CSV written: {args.csv_out}")
    if do_geocode:
        total_groups = len(set(r.location_group for r in records))
        print(f"Geocoded groups: {geocode_success_groups}/{total_groups}")
    print(f"Mode: {'DRY RUN (no renaming)' if args.dry_run else 'RENAMED'}")


if __name__ == "__main__":
    main()

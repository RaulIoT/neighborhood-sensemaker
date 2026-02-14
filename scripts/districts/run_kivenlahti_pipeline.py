#!/usr/bin/env python3
"""One-command pipeline for Kivenlahti photos.

Steps:
1) Rename photos in-place and build index CSV.
2) Run ChatGPT labeling on the index CSV.
3) Add `photo_path` column for QGIS image preview.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Kivenlahti rename + ChatGPT labeling pipeline.")
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    p.add_argument("--input-dir", type=Path, default=Path("Kivenlahti_photos"))
    p.add_argument("--prefix", default="Kivenlahti")
    p.add_argument("--index-csv", type=Path, default=Path("Data/kivenlahti_photo_index.csv"))
    p.add_argument("--ai-csv", type=Path, default=Path("Data/kivenlahti_photo_index_ai.csv"))
    p.add_argument("--limit", type=int, default=0, help="Optional limit for ChatGPT labeling (0 = all).")
    p.add_argument("--skip-rename", action="store_true", help="Skip rename/index step and use existing index CSV.")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def run_cmd(cmd: list[str], cwd: Path) -> None:
    printable = " ".join(cmd)
    print(f"\n$ {printable}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def add_photo_path_column(ai_csv: Path, photo_dir: Path) -> int:
    with ai_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = list(reader.fieldnames or [])

    if "photo_path" not in fields:
        fields.append("photo_path")

    for row in rows:
        name = (row.get("new_name") or row.get("original_name") or "").strip()
        row["photo_path"] = str((photo_dir / name).resolve()) if name else ""

    with ai_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    input_dir = (root / args.input_dir).resolve() if not args.input_dir.is_absolute() else args.input_dir
    index_csv = (root / args.index_csv).resolve() if not args.index_csv.is_absolute() else args.index_csv
    ai_csv = (root / args.ai_csv).resolve() if not args.ai_csv.is_absolute() else args.ai_csv

    if not input_dir.exists():
        raise SystemExit(f"Input directory not found: {input_dir}")

    py = sys.executable

    rename_script = root / "scripts" / "districts" / "rename_geotagged_photos.py"
    label_script = root / "scripts" / "districts" / "ChatGPT_photo_labeler.py"

    if not args.skip_rename:
        run_cmd(
            [
                py,
                str(rename_script),
                "--input-dir",
                str(input_dir),
                "--prefix",
                args.prefix,
                "--csv-out",
                str(index_csv),
            ],
            cwd=root,
        )
    else:
        if not index_csv.exists():
            raise SystemExit(f"--skip-rename was set but index CSV not found: {index_csv}")

    label_cmd = [
        py,
        str(label_script),
        "--input-csv",
        str(index_csv),
        "--output-csv",
        str(ai_csv),
        "--photo-dir",
        str(input_dir),
    ]
    if args.limit > 0:
        label_cmd.extend(["--limit", str(args.limit)])
    if args.verbose:
        label_cmd.append("--verbose")

    run_cmd(label_cmd, cwd=root)

    row_count = add_photo_path_column(ai_csv=ai_csv, photo_dir=input_dir)

    print("\nPipeline complete")
    print(f"Index CSV: {index_csv}")
    print(f"AI CSV: {ai_csv}")
    print(f"Rows with photo_path updated: {row_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

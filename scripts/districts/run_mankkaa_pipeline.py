#!/usr/bin/env python3
"""One-command pipeline for Mankkaa photos (Light + Dark).

Steps for each set:
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


def run_cmd(cmd: list[str], cwd: Path) -> None:
    print(f"\n$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def add_photo_path_column(ai_csv: Path, photo_dir: Path) -> int:
    with ai_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fields = list(reader.fieldnames or [])

    if "photo_path" not in fields:
        fields.append("photo_path")

    for row in rows:
        original = (row.get("original_name") or "").strip()
        new_name = (row.get("new_name") or "").strip()

        candidates: list[Path] = []
        if new_name:
            candidates.append(photo_dir / new_name)
        if original:
            candidates.append(photo_dir / original)

        chosen = ""
        for candidate in candidates:
            if candidate.exists():
                chosen = str(candidate.resolve())
                break
        if not chosen and candidates:
            chosen = str(candidates[0].resolve())

        row["photo_path"] = chosen

    with ai_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def run_set(
    *,
    root: Path,
    py: str,
    photo_dir: Path,
    prefix: str,
    index_csv: Path,
    ai_csv: Path,
    limit: int,
    skip_rename: bool,
    verbose: bool,
) -> None:
    if not photo_dir.exists():
        raise SystemExit(f"Photo directory not found: {photo_dir}")

    rename_script = root / "scripts" / "districts" / "rename_geotagged_photos.py"
    label_script = root / "scripts" / "districts" / "ChatGPT_photo_labeler.py"

    if not skip_rename:
        run_cmd(
            [
                py,
                str(rename_script),
                "--input-dir",
                str(photo_dir),
                "--prefix",
                prefix,
                "--csv-out",
                str(index_csv),
            ],
            cwd=root,
        )
    else:
        if not index_csv.exists():
            raise SystemExit(f"--skip-rename set but index CSV not found: {index_csv}")

    label_cmd = [
        py,
        str(label_script),
        "--input-csv",
        str(index_csv),
        "--output-csv",
        str(ai_csv),
        "--photo-dir",
        str(photo_dir),
    ]
    if limit > 0:
        label_cmd.extend(["--limit", str(limit)])
    if verbose:
        label_cmd.append("--verbose")

    run_cmd(label_cmd, cwd=root)

    rows = add_photo_path_column(ai_csv=ai_csv, photo_dir=photo_dir)
    print(f"Updated photo_path in {ai_csv} ({rows} rows)")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Mankkaa Light+Dark rename + ChatGPT labeling pipeline.")
    p.add_argument("--project-root", type=Path, default=Path.cwd())

    p.add_argument("--light-dir", type=Path, default=Path("Mankkaa_photos/Light"))
    p.add_argument("--light-prefix", default="MankkaaLight")
    p.add_argument("--light-index-csv", type=Path, default=Path("Data/mankkaa_light_photo_index.csv"))
    p.add_argument("--light-ai-csv", type=Path, default=Path("Data/mankkaa_light_photo_index_ai.csv"))

    p.add_argument("--dark-dir", type=Path, default=Path("Mankkaa_photos/Dark"))
    p.add_argument("--dark-prefix", default="MankkaaDark")
    p.add_argument("--dark-index-csv", type=Path, default=Path("Data/mankkaa_dark_photo_index.csv"))
    p.add_argument("--dark-ai-csv", type=Path, default=Path("Data/mankkaa_dark_photo_index_ai.csv"))

    p.add_argument("--limit", type=int, default=0, help="Optional label limit per set (0 = all).")
    p.add_argument("--skip-rename", action="store_true", help="Skip rename/index step for both sets.")
    p.add_argument("--skip-light", action="store_true")
    p.add_argument("--skip-dark", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def resolve_path(root: Path, p: Path) -> Path:
    return p.resolve() if p.is_absolute() else (root / p).resolve()


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    py = sys.executable

    light_dir = resolve_path(root, args.light_dir)
    light_index_csv = resolve_path(root, args.light_index_csv)
    light_ai_csv = resolve_path(root, args.light_ai_csv)

    dark_dir = resolve_path(root, args.dark_dir)
    dark_index_csv = resolve_path(root, args.dark_index_csv)
    dark_ai_csv = resolve_path(root, args.dark_ai_csv)

    if not args.skip_light:
        print("\n=== Mankkaa Light ===")
        run_set(
            root=root,
            py=py,
            photo_dir=light_dir,
            prefix=args.light_prefix,
            index_csv=light_index_csv,
            ai_csv=light_ai_csv,
            limit=args.limit,
            skip_rename=args.skip_rename,
            verbose=args.verbose,
        )

    if not args.skip_dark:
        print("\n=== Mankkaa Dark ===")
        run_set(
            root=root,
            py=py,
            photo_dir=dark_dir,
            prefix=args.dark_prefix,
            index_csv=dark_index_csv,
            ai_csv=dark_ai_csv,
            limit=args.limit,
            skip_rename=args.skip_rename,
            verbose=args.verbose,
        )

    print("\nPipeline complete")
    if not args.skip_light:
        print(f"Light AI CSV: {light_ai_csv}")
    if not args.skip_dark:
        print(f"Dark AI CSV: {dark_ai_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

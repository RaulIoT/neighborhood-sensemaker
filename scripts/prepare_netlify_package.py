#!/usr/bin/env python3
"""Prepare a sanitized qgis2web folder for Netlify deployment.

What it does:
1) Copies the web export folder to a target deploy folder.
2) Strips EXIF metadata from images in `images/` (requires Pillow).
3) Scans text files for absolute local paths and secret-like patterns.
4) Writes a short report with findings.
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {
    ".html",
    ".htm",
    ".js",
    ".css",
    ".json",
    ".geojson",
    ".csv",
    ".txt",
    ".md",
    ".xml",
    ".yml",
    ".yaml",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}

PATH_PATTERNS = [
    re.compile(r"/Users/[^\s\"']+"),
    re.compile(r"C:\\\\Users\\\\[^\\s\"']+"),
    re.compile(r"/home/[^\s\"']+"),
]

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z\\-_]{20,}"),
    re.compile(r"(?i)api[_-]?key\\s*[:=]\\s*['\"][^'\"]+['\"]"),
    re.compile(r"(?i)token\\s*[:=]\\s*['\"][^'\"]+['\"]"),
]


def find_text_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS:
            yield path


def find_image_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def strip_exif_images(images: list[Path]) -> tuple[int, int]:
    try:
        from PIL import Image
    except Exception:
        return 0, len(images)

    cleaned = 0
    failed = 0
    for image_path in images:
        try:
            with Image.open(image_path) as img:
                pixels = list(img.getdata())
                mode = img.mode
                size = img.size
                out = Image.new(mode, size)
                out.putdata(pixels)
                save_kwargs = {}
                if image_path.suffix.lower() in {".jpg", ".jpeg"}:
                    save_kwargs["quality"] = 95
                    save_kwargs["optimize"] = True
                out.save(image_path, **save_kwargs)
                cleaned += 1
        except Exception:
            failed += 1
    return cleaned, failed


def scan_text_for_patterns(files: list[Path], root: Path) -> list[str]:
    findings: list[str] = []
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = file_path.relative_to(root)
        for pattern in PATH_PATTERNS:
            for m in pattern.findall(content):
                findings.append(f"{rel}: absolute-path -> {m}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                findings.append(f"{rel}: potential-secret-pattern")
    return findings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default=".",
        help="Source qgis2web folder",
    )
    parser.add_argument(
        "--target",
        default="../SPT_Map_Final_sanitized",
        help="Output folder for sanitized deployment package",
    )
    args = parser.parse_args()

    source = Path(args.source)
    target = Path(args.target)

    if not source.exists():
        raise SystemExit(f"Source does not exist: {source}")

    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)

    image_files = list(find_image_files(target / "images")) if (target / "images").exists() else []
    cleaned, failed = strip_exif_images(image_files)

    text_files = list(find_text_files(target))
    findings = scan_text_for_patterns(text_files, target)

    report = []
    report.append("Netlify Sanitization Report")
    report.append(f"Source: {source}")
    report.append(f"Target: {target}")
    report.append("")
    report.append(f"Images found: {len(image_files)}")
    report.append(f"Images EXIF-cleaned: {cleaned}")
    report.append(f"Images EXIF-clean-failed: {failed}")
    report.append("")
    report.append(f"Text files scanned: {len(text_files)}")
    report.append(f"Findings: {len(findings)}")
    report.extend(findings if findings else ["No path/secret findings."])
    report_text = "\n".join(report) + "\n"

    report_path = target / "SANITIZE_REPORT.txt"
    report_path.write_text(report_text, encoding="utf-8")
    print(report_text, end="")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Label photo-based urban experience dimensions with OpenAI vision.

Reads an input CSV, finds each photo, and appends AI-only columns:
- AI-Social_environment
- AI-Active_environment
- AI-Aesthetic_environment
- AI-Atmosphere
- AI_significance

Plus per-dimension explanations for why AI chose each label.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
from pathlib import Path
from typing import Any

import requests


LABEL_VALUES = {"Negative", "Neutral", "Positive"}
NEW_COLUMNS = [
    "AI-Social_environment",
    "AI-Active_environment",
    "AI-Aesthetic_environment",
    "AI-Atmosphere",
    "AI_significance",
    "AI_Social_environment_reason",
    "AI_Active_environment_reason",
    "AI_Aesthetic_environment_reason",
    "AI_Atmosphere_reason",
    "AI_significance_reason",
    "AI_confidence",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Append AI-only urban-experience labels + explanations to a CSV using ChatGPT vision."
    )
    p.add_argument("--input-csv", type=Path, default=Path("Data/leppavaara_photo_index_sample3.csv"))
    p.add_argument("--output-csv", type=Path, default=Path("Data/leppavaara_photo_index_ai.csv"))
    p.add_argument("--photo-dir", type=Path, default=Path("Leppävaara_photos"))
    p.add_argument("--env-file", type=Path, default=Path(".env"))
    p.add_argument("--openai-api-key", default=None)
    p.add_argument("--model", default="gpt-4.1-mini")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--limit", type=int, default=0, help="Process at most N rows (0 = all).")
    p.add_argument(
        "--skip-if-filled",
        action="store_true",
        help="Skip rows that already have all AI label columns filled.",
    )
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def load_simple_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def extract_text_from_openai_response(data: dict[str, Any]) -> str:
    text = ""
    for choice in data.get("choices", []):
        msg = choice.get("message", {}) or {}
        content = msg.get("content", "")
        if isinstance(content, str):
            text += content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text += str(part.get("text", ""))
    return text


def normalize_label(value: Any) -> str:
    s = str(value or "").strip().lower()
    if s in {"negative", "neg"}:
        return "Negative"
    if s in {"neutral", "neu"}:
        return "Neutral"
    if s in {"positive", "pos"}:
        return "Positive"
    return ""


def clean_reason(value: Any) -> str:
    s = str(value or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def call_openai_photo_labels(
    *,
    image_bytes: bytes,
    api_key: str,
    model: str,
    timeout: int,
    verbose: bool = False,
) -> dict[str, Any] | None:
    prompt = (
        "Assess the place shown in one urban photo. Return ONLY JSON with keys:\n"
        "social_label, social_reason, active_label, active_reason, "
        "aesthetic_label, aesthetic_reason, atmosphere_label, atmosphere_reason, "
        "significance_label, significance_reason, confidence.\n"
        "Rules:\n"
        "- Labels must be exactly one of: Negative, Neutral, Positive.\n"
        "- Each *_reason must be one short concrete sentence based on visible cues.\n"
        "- confidence must be 0..1."
    )

    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 350,
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except Exception as exc:
        if verbose:
            print(f"OpenAI request failed: {exc}")
        return None
    if resp.status_code >= 400:
        if verbose:
            print(f"OpenAI API error: status={resp.status_code} body={(resp.text or '')[:220]}")
        return None
    data = resp.json()
    text = extract_text_from_openai_response(data)
    parsed = parse_json_object(text)
    if not parsed:
        if verbose:
            print(f"OpenAI parse failed. Raw text: {(text or '')[:220]}")
        return None

    out = {
        "AI-Social_environment": normalize_label(parsed.get("social_label")),
        "AI-Active_environment": normalize_label(parsed.get("active_label")),
        "AI-Aesthetic_environment": normalize_label(parsed.get("aesthetic_label")),
        "AI-Atmosphere": normalize_label(parsed.get("atmosphere_label")),
        "AI_significance": normalize_label(parsed.get("significance_label")),
        "AI_Social_environment_reason": clean_reason(parsed.get("social_reason")),
        "AI_Active_environment_reason": clean_reason(parsed.get("active_reason")),
        "AI_Aesthetic_environment_reason": clean_reason(parsed.get("aesthetic_reason")),
        "AI_Atmosphere_reason": clean_reason(parsed.get("atmosphere_reason")),
        "AI_significance_reason": clean_reason(parsed.get("significance_reason")),
        "AI_confidence": "",
    }
    try:
        conf = float(parsed.get("confidence", ""))
        if conf < 0:
            conf = 0.0
        if conf > 1:
            conf = 1.0
        out["AI_confidence"] = f"{conf:.3f}"
    except Exception:
        out["AI_confidence"] = ""

    # Require valid labels so output stays clean and predictable.
    for key in [
        "AI-Social_environment",
        "AI-Active_environment",
        "AI-Aesthetic_environment",
        "AI-Atmosphere",
        "AI_significance",
    ]:
        if out[key] not in LABEL_VALUES:
            out[key] = ""

    return out


def resolve_photo_path(row: dict[str, str], photo_dir: Path, input_csv: Path) -> Path | None:
    candidates = []
    for key in ("new_name", "original_name"):
        name = str(row.get(key, "")).strip()
        if name:
            candidates.append(photo_dir / name)
            candidates.append(input_csv.parent / name)
            candidates.append(Path(name))

    seen: set[Path] = set()
    for path in candidates:
        try:
            rp = path.resolve()
        except Exception:
            rp = path
        if rp in seen:
            continue
        seen.add(rp)
        if path.exists() and path.is_file():
            return path
    return None


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    return fields, rows


def write_rows(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def is_filled(row: dict[str, str]) -> bool:
    return all(str(row.get(c, "")).strip() for c in NEW_COLUMNS[:5])


def main() -> int:
    args = parse_args()
    load_simple_dotenv(args.env_file)

    api_key = args.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("Missing OPENAI_API_KEY. Set it in .env or pass --openai-api-key.")
    if not args.input_csv.exists():
        raise SystemExit(f"Input CSV not found: {args.input_csv}")

    fields, rows = read_rows(args.input_csv)
    for col in NEW_COLUMNS:
        if col not in fields:
            fields.append(col)

    processed = 0
    skipped_filled = 0
    missing_image = 0
    failed = 0

    for idx, row in enumerate(rows, start=1):
        if args.limit > 0 and processed >= args.limit:
            break

        if args.skip_if_filled and is_filled(row):
            skipped_filled += 1
            continue

        image_path = resolve_photo_path(row, args.photo_dir, args.input_csv)
        if image_path is None:
            missing_image += 1
            for col in NEW_COLUMNS:
                row[col] = row.get(col, "")
            row["AI_Social_environment_reason"] = row.get("AI_Social_environment_reason", "image_not_found")
            continue

        try:
            labels = call_openai_photo_labels(
                image_bytes=image_path.read_bytes(),
                api_key=api_key,
                model=args.model,
                timeout=args.timeout,
                verbose=args.verbose,
            )
            if labels is None:
                failed += 1
                continue
            row.update(labels)
            processed += 1
            if args.verbose:
                print(f"[{idx}/{len(rows)}] labeled {image_path.name}")
        except Exception:
            failed += 1

    write_rows(args.output_csv, fields, rows)

    print(f"Rows total: {len(rows)}")
    print(f"Labeled rows: {processed}")
    print(f"Skipped already-filled: {skipped_filled}")
    print(f"Missing image: {missing_image}")
    print(f"Failed API/parse: {failed}")
    print(f"CSV written: {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

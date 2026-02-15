# SPT Map Final (Netlify + Python Pipeline)

This folder is now a standalone Git repo for:
- The deployable web map (`index.html`, `css/`, `js/`, `images/`, `data/`)
- A minimal, reusable Python pipeline for photo indexing and AI labeling

## Included Python scripts

- `scripts/prepare_netlify_package.py`
- `scripts/districts/rename_geotagged_photos.py`
- `scripts/districts/ChatGPT_photo_labeler.py`
- `scripts/districts/run_kivenlahti_pipeline.py`
- `scripts/districts/run_mankkaa_pipeline.py`

These were copied from the parent `VS_Code/scripts` area into this repo.

## Security and data safety

- No API keys are stored in code here.
- `.env` and secret-like files are git-ignored via `.gitignore`.
- `Group task 2` content was not imported into this repo.

## Attribution and licenses

- This project is released under the MIT License (see `LICENSE`).
- Basemap data © OpenStreetMap contributors (ODbL). Tiles/styles and third-party components: see `THIRD_PARTY_NOTICES.md`.
- Generated using QGIS + qgis2web.
- If this site is deployed publicly, review provider terms for `tile.openstreetmap.org` and `data.osmbuildings.org` before scaling traffic.

## Setup

```bash
cd "Data/netlify_ready/SPT_Map_Final"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set API key only in shell or `.env` (never commit `.env`):

```bash
export OPENAI_API_KEY="your_key_here"
```

## Pipeline usage

### 1) Kivenlahti pipeline

Expected input photo folder (default):
- `Kivenlahti_photos/`

Run:

```bash
python scripts/districts/run_kivenlahti_pipeline.py --project-root .
```

Outputs (default):
- `Data/kivenlahti_photo_index.csv`
- `Data/kivenlahti_photo_index_ai.csv`

### 2) Mankkaa Light + Dark pipeline

Expected input photo folders (default):
- `Mankkaa_photos/Light`
- `Mankkaa_photos/Dark`

Run:

```bash
python scripts/districts/run_mankkaa_pipeline.py --project-root .
```

Outputs (default):
- `Data/mankkaa_light_photo_index.csv`
- `Data/mankkaa_light_photo_index_ai.csv`
- `Data/mankkaa_dark_photo_index.csv`
- `Data/mankkaa_dark_photo_index_ai.csv`

### 3) Optional: sanitize a deploy package

```bash
python scripts/prepare_netlify_package.py --source . --target ../SPT_Map_Final_sanitized
```

This checks text files for potential path/secret leakage and can strip EXIF metadata from images.

## Git / GitHub quick start

```bash
git add .
git commit -m "Initial SPT_Map_Final repo with map + pipeline scripts"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

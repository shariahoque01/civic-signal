"""Export a read-only static snapshot of the app (frontend + current data) for Vercel.

    python -m scripts.export_static            # writes ../dist
    cd ../dist && vercel deploy --prod

The snapshot serves the same frontend; api.js sees window.CIVIC_SNAPSHOT and reads
data/*.json instead of the API. Write actions (311 status, add video) are disabled.
"""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
ENDPOINTS = {
    "videos.json": "/api/videos?days=365",
    "cases.json": "/api/cases",
    "insights.json": "/api/insights",
}


def main(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(FRONTEND, out)
    (out / "data").mkdir()
    with TestClient(app) as client:
        for name, path in ENDPOINTS.items():
            resp = client.get(path)
            resp.raise_for_status()
            (out / "data" / name).write_text(json.dumps(resp.json()))
            print(f"{name:14} {len(resp.content) / 1024:7.0f} KB  <- {path}")
    exported_at = datetime.now(timezone.utc).isoformat()
    index = out / "index.html"
    index.write_text(index.read_text().replace(
        "<head>", f'<head>\n<script>window.CIVIC_SNAPSHOT = {{ exported_at: "{exported_at}" }};</script>', 1))
    print(f"Snapshot written to {out} (exported {exported_at})")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist")

#!/usr/bin/env python3
"""
Descarga fotos de Google Places para todos los lugares que aún no tienen fotos.
Requiere que populate_from_google.py haya corrido antes.

Uso (desde la raíz del proyecto):
    python scripts/download_photos.py
"""

import json
import os
import pathlib
import sys
import time

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY      = os.getenv("GOOGLE_PLACES_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
PHOTOS_DIR   = pathlib.Path("static/photos")


def _request_with_backoff(fn, max_retries=5):
    for attempt in range(max_retries):
        try:
            return fn()
        except requests.HTTPError as e:
            status = e.response.status_code
            if status == 403:
                print("\nERROR 403: revisa que la Places API (New) esté habilitada y el billing activo.")
                sys.exit(1)
            if status == 429 and attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"    429 rate limit — esperando {wait}s...")
                time.sleep(wait)
            else:
                raise


def get_photo_refs(place_id: str) -> list[str]:
    def _call():
        resp = requests.get(
            f"https://places.googleapis.com/v1/places/{place_id}",
            headers={"X-Goog-Api-Key": API_KEY, "X-Goog-FieldMask": "photos.name"},
            timeout=15,
        )
        resp.raise_for_status()
        return [p["name"] for p in resp.json().get("photos", [])[:2]]
    return _request_with_backoff(_call)


def download_photo(photo_name: str, filename: str) -> str | None:
    def _call():
        resp = requests.get(
            f"https://places.googleapis.com/v1/{photo_name}/media",
            params={"maxHeightPx": 800, "maxWidthPx": 1200, "key": API_KEY},
            allow_redirects=True,
            timeout=30,
        )
        resp.raise_for_status()
        return resp
    try:
        resp = _request_with_backoff(_call)
        if resp.content:
            (PHOTOS_DIR / filename).write_bytes(resp.content)
            return f"{API_BASE_URL}/static/photos/{filename}"
    except Exception as e:
        print(f"      ERROR descargando foto: {e}")
    return None


def main():
    if not API_KEY:
        print("ERROR: GOOGLE_PLACES_API_KEY no está definida en .env")
        sys.exit(1)

    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    cur.execute("""
        SELECT id, google_place_id, name
        FROM places
        WHERE google_place_id IS NOT NULL
          AND (photos = '[]'::jsonb OR photos IS NULL)
        ORDER BY id
    """)
    pending = cur.fetchall()

    if not pending:
        print("No hay lugares pendientes de fotos.")
        conn.close()
        return

    print(f"Lugares sin fotos: {len(pending)}\n")
    updated = errors = 0

    for i, (place_id, google_id, name) in enumerate(pending, 1):
        try:
            refs = get_photo_refs(google_id)
            time.sleep(0.3)

            if not refs:
                print(f"  [{i}/{len(pending)}] - {name}: sin fotos en Google")
                continue

            photo_urls = []
            for j, ref in enumerate(refs):
                url = download_photo(ref, f"{google_id}_{j}.jpg")
                if url:
                    photo_urls.append(url)
                time.sleep(0.3)

            if photo_urls:
                cur.execute(
                    "UPDATE places SET photos = %s WHERE id = %s",
                    (json.dumps(photo_urls), place_id),
                )
                updated += 1
                print(f"  [{i}/{len(pending)}] ✓ {name} — {len(photo_urls)} foto(s)")
            else:
                print(f"  [{i}/{len(pending)}] - {name}: no se pudieron descargar fotos")

        except SystemExit:
            raise
        except Exception as e:
            errors += 1
            print(f"  [{i}/{len(pending)}] ERROR {name}: {e}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nListo. Actualizados: {updated} | Errores: {errors}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Pobla la base de datos con lugares reales de Asunción usando Google Places API (New).

Estrategia: grilla de 16 puntos (4x4) con radio de 2.5km, cubriendo toda la ciudad.
Por cada punto se buscan las 6 categorías de la app.

Uso (desde la raíz del proyecto):
    python scripts/populate_from_google.py
"""

import json
import os
import pathlib
import re
import sys
import time

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
PHOTOS_DIR = pathlib.Path("static/photos")

# Grilla de búsqueda sobre Asunción (4 filas × 4 columnas = 16 puntos)
GRID_LATS = [-25.21, -25.27, -25.32, -25.38]
GRID_LNGS = [-57.56, -57.61, -57.66, -57.71]
SEARCH_RADIUS = 2500.0  # metros

# Tipos de Google Places que buscamos por cada categoría de la app.
# La primera categoría cuyo tipo coincida en el lugar gana.
CATEGORY_TYPES = {
    "restaurant": ["restaurant", "cafe", "bakery"],
    "museum":     ["museum", "art_gallery", "cultural_center"],
    "park":       ["park", "national_park", "botanical_garden", "zoo"],
    "hotel":      ["hotel", "motel", "resort_hotel"],
    "bar":        ["bar", "night_club"],
    "attraction": ["tourist_attraction", "historical_landmark", "church"],
}

TYPE_TO_CATEGORY = {
    t: cat for cat, types in CATEGORY_TYPES.items() for t in types
}

DAYS_EN_ES = {
    "Monday":    "lunes",
    "Tuesday":   "martes",
    "Wednesday": "miércoles",
    "Thursday":  "jueves",
    "Friday":    "viernes",
    "Saturday":  "sábado",
    "Sunday":    "domingo",
}

BASE_HEADERS = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": API_KEY,
}


# ---------------------------------------------------------------------------
# Google Places API (New)
# ---------------------------------------------------------------------------

def _request_with_backoff(fn, max_retries=5):
    """Ejecuta fn() reintentando con backoff exponencial ante errores 429."""
    for attempt in range(max_retries):
        try:
            return fn()
        except requests.HTTPError as e:
            if e.response.status_code == 429 and attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s, 16s
                print(f"    429 rate limit — esperando {wait}s antes de reintentar...")
                time.sleep(wait)
            else:
                raise


def nearby_search(lat: float, lng: float, google_type: str) -> list[str]:
    def _call():
        resp = requests.post(
            "https://places.googleapis.com/v1/places:searchNearby",
            json={
                "includedTypes": [google_type],
                "maxResultCount": 20,
                "locationRestriction": {
                    "circle": {
                        "center": {"latitude": lat, "longitude": lng},
                        "radius": SEARCH_RADIUS,
                    }
                },
                "languageCode": "es",
            },
            headers={**BASE_HEADERS, "X-Goog-FieldMask": "places.id"},
            timeout=15,
        )
        resp.raise_for_status()
        return [p["id"] for p in resp.json().get("places", [])]
    return _request_with_backoff(_call)


def get_place_details(place_id: str) -> dict:
    fields = ",".join([
        "id", "displayName", "types", "formattedAddress",
        "nationalPhoneNumber", "websiteUri", "rating",
        "userRatingCount", "regularOpeningHours", "photos", "location",
    ])
    def _call():
        resp = requests.get(
            f"https://places.googleapis.com/v1/places/{place_id}",
            params={"languageCode": "es"},
            headers={**BASE_HEADERS, "X-Goog-FieldMask": fields},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
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
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Parseo de horarios
# ---------------------------------------------------------------------------

def _to_24h(time_str: str) -> str:
    time_str = time_str.strip()
    m = re.match(r"(\d+):(\d+)\s*(AM|PM)", time_str, re.IGNORECASE)
    if not m:
        return time_str
    h, mins, period = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if period == "PM" and h != 12:
        h += 12
    elif period == "AM" and h == 12:
        h = 0
    return f"{h:02d}:{mins:02d}"


def _parse_time_range(raw: str) -> str:
    segment = raw.split(",")[0].strip()
    for sep in ["–", "-"]:
        if sep in segment:
            a, b = segment.split(sep, 1)
            return f"{_to_24h(a)} - {_to_24h(b)}"
    return segment


def parse_opening_hours(regular_opening_hours: dict | None) -> dict | None:
    if not regular_opening_hours:
        return None
    result = {}
    for desc in regular_opening_hours.get("weekdayDescriptions", []):
        if ": " not in desc:
            continue
        day_en, hours_raw = desc.split(": ", 1)
        day_es = DAYS_EN_ES.get(day_en, day_en.lower())
        if "Closed" in hours_raw or "Cerrado" in hours_raw:
            result[day_es] = "Cerrado"
        elif "24 hour" in hours_raw or "24 hora" in hours_raw:
            result[day_es] = "24 horas"
        else:
            result[day_es] = _parse_time_range(hours_raw)
    return result or None


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

def insert_place(cur, details: dict, category: str, photo_urls: list[str]) -> bool:
    loc = details.get("location", {})
    hours = details.get("regularOpeningHours")
    cur.execute(
        """
        INSERT INTO places (
            google_place_id, name, category, address, phone, website,
            rating, total_ratings, opening_hours, location, photos
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
            ST_MakePoint(%s, %s)::geography, %s)
        ON CONFLICT (google_place_id) DO NOTHING
        RETURNING id
        """,
        (
            details["id"],
            details.get("displayName", {}).get("text", "Sin nombre"),
            category,
            details.get("formattedAddress"),
            details.get("nationalPhoneNumber"),
            details.get("websiteUri"),
            details.get("rating"),
            details.get("userRatingCount"),
            json.dumps(parse_opening_hours(hours)) if hours else None,
            loc.get("longitude"),
            loc.get("latitude"),
            json.dumps(photo_urls),
        ),
    )
    return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not API_KEY:
        print("ERROR: GOOGLE_PLACES_API_KEY no está definida en .env")
        sys.exit(1)

    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # --- Fase 1: recolectar IDs únicos ---
    print("Fase 1: buscando lugares en la grilla...\n")
    found: dict[str, str] = {}  # place_id -> category
    total = len(GRID_LATS) * len(GRID_LNGS) * sum(len(v) for v in CATEGORY_TYPES.values())
    n = 0

    for lat in GRID_LATS:
        for lng in GRID_LNGS:
            for category, types in CATEGORY_TYPES.items():
                for gtype in types:
                    n += 1
                    try:
                        ids = nearby_search(lat, lng, gtype)
                        new_ids = [i for i in ids if i not in found]
                        for pid in new_ids:
                            found[pid] = category
                        print(f"  [{n}/{total}] ({lat:.2f},{lng:.2f}) {gtype:25s} → {len(ids):2d} resultados, {len(new_ids):2d} nuevos")
                    except Exception as e:
                        print(f"  [{n}/{total}] ERROR ({lat:.2f},{lng:.2f}) {gtype}: {e}")
                    time.sleep(1)

    print(f"\nTotal lugares únicos: {len(found)}\n")

    # --- Fase 2: detalles + fotos + inserción ---
    print("Fase 2: descargando detalles y fotos...\n")
    inserted = skipped = errors = 0

    for i, (place_id, category) in enumerate(found.items(), 1):
        try:
            details = get_place_details(place_id)
            time.sleep(0.5)

            # Categoría: preferir inferencia desde los tipos del lugar
            place_types = details.get("types", [])
            final_category = next(
                (TYPE_TO_CATEGORY[t] for t in place_types if t in TYPE_TO_CATEGORY),
                category,
            )

            # Descargar hasta 2 fotos
            photo_urls = []
            for j, photo in enumerate(details.get("photos", [])[:2]):
                url = download_photo(photo["name"], f"{place_id}_{j}.jpg")
                if url:
                    photo_urls.append(url)
                time.sleep(0.5)

            was_inserted = insert_place(cur, details, final_category, photo_urls)

            name = details.get("displayName", {}).get("text", place_id)
            if was_inserted:
                inserted += 1
                print(f"  [{i}/{len(found)}] ✓ {name} ({final_category})")
            else:
                skipped += 1
                print(f"  [{i}/{len(found)}] ~ ya existe: {name}")

        except Exception as e:
            errors += 1
            print(f"  [{i}/{len(found)}] ERROR {place_id}: {e}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"""
Listo.
  Insertados:  {inserted}
  Ya existían: {skipped}
  Errores:     {errors}
""")


if __name__ == "__main__":
    main()

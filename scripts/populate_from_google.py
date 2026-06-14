#!/usr/bin/env python3
"""
Pobla la base de datos con lugares reales de Asunción usando Google Places API (New).

Estrategia: grilla de 9 puntos (3x3) centrada en Asunción, radio 1.5km.
Solo se insertan lugares cuya dirección contiene "Asunción"/"Asuncion".

Las fotos NO se descargan ahora — se guardan las referencias de Google en la
columna google_place_id para poder ejecutar scripts/download_photos.py después.

Uso (desde la raíz del proyecto):
    python scripts/populate_from_google.py
"""

import json
import os
import re
import sys
import time

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY      = os.getenv("GOOGLE_PLACES_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Cambiar a None para traer todos los lugares de Asunción.
LIMIT = None

# Grilla 3×3 centrada en Asunción (9 puntos, radio 1500m).
# Puntos ajustados para no caer en municipios vecinos.
GRID_LATS = [-25.26, -25.30, -25.34]
GRID_LNGS = [-57.62, -57.66, -57.70]
SEARCH_RADIUS = 1500.0  # metros

# Tipos de Google → categoría de la app.
CATEGORY_TYPES = {
    "restaurant": ["restaurant", "cafe", "bakery"],
    "museum":     ["museum", "art_gallery", "cultural_center"],
    "park":       ["park", "botanical_garden", "zoo"],
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
    for attempt in range(max_retries):
        try:
            return fn()
        except requests.HTTPError as e:
            status = e.response.status_code
            if status == 403:
                print("\nERROR 403: La Places API (New) no está habilitada o la key es incorrecta.")
                sys.exit(1)
            if status == 429 and attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"    429 rate limit — esperando {wait}s...")
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
        "userRatingCount", "regularOpeningHours", "location",
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


def is_in_asuncion(address: str | None) -> bool:
    if not address:
        return False
    return "asunci" in address.lower()


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

def truncate_places(cur):
    cur.execute("TRUNCATE route_places, places RESTART IDENTITY CASCADE")
    print("Tabla places vaciada.\n")


def insert_place(cur, details: dict, category: str) -> bool:
    loc   = details.get("location", {})
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
            json.dumps([]),  # fotos vacías — completar con download_photos.py
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

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    truncate_places(cur)
    conn.commit()

    # --- Fase 1: recolectar IDs únicos en la grilla ---
    print("Fase 1: buscando lugares en la grilla de Asunción...\n")
    found: dict[str, str] = {}  # place_id -> category
    total = len(GRID_LATS) * len(GRID_LNGS) * sum(len(v) for v in CATEGORY_TYPES.values())
    n = 0

    for lat in GRID_LATS:
        for lng in GRID_LNGS:
            for category, types in CATEGORY_TYPES.items():
                for gtype in types:
                    if LIMIT and len(found) >= LIMIT:
                        break
                    n += 1
                    try:
                        ids = nearby_search(lat, lng, gtype)
                        new_ids = [i for i in ids if i not in found]
                        for pid in new_ids:
                            found[pid] = category
                        print(f"  [{n}/{total}] ({lat:.2f},{lng:.2f}) {gtype:25s} → {len(ids):2d} resultados, {len(new_ids):2d} nuevos")
                    except SystemExit:
                        raise
                    except Exception as e:
                        print(f"  [{n}/{total}] ERROR ({lat:.2f},{lng:.2f}) {gtype}: {e}")
                    time.sleep(1)
                if LIMIT and len(found) >= LIMIT:
                    break
            if LIMIT and len(found) >= LIMIT:
                break
        if LIMIT and len(found) >= LIMIT:
            break

    places_to_process = dict(list(found.items())[:LIMIT] if LIMIT else found.items())
    print(f"\nTotal únicos encontrados: {len(found)} — a procesar: {len(places_to_process)}\n")

    # --- Fase 2: detalles + filtro Asunción + inserción ---
    print("Fase 2: obteniendo detalles e insertando...\n")
    inserted = skipped = filtered = errors = 0

    for i, (place_id, category) in enumerate(places_to_process.items(), 1):
        try:
            details = get_place_details(place_id)
            time.sleep(0.5)

            address = details.get("formattedAddress", "")

            # Filtro: solo lugares de Asunción
            if not is_in_asuncion(address):
                filtered += 1
                name = details.get("displayName", {}).get("text", place_id)
                print(f"  [{i}/{len(places_to_process)}] ✗ fuera de Asunción: {name} — {address}")
                continue

            # Categoría: preferir inferencia desde los tipos del lugar
            place_types    = details.get("types", [])
            final_category = next(
                (TYPE_TO_CATEGORY[t] for t in place_types if t in TYPE_TO_CATEGORY),
                category,
            )

            was_inserted = insert_place(cur, details, final_category)
            name = details.get("displayName", {}).get("text", place_id)

            if was_inserted:
                inserted += 1
                print(f"  [{i}/{len(places_to_process)}] ✓ {name} ({final_category})")
            else:
                skipped += 1
                print(f"  [{i}/{len(places_to_process)}] ~ ya existe: {name}")

        except SystemExit:
            raise
        except Exception as e:
            errors += 1
            print(f"  [{i}/{len(places_to_process)}] ERROR {place_id}: {e}")

    conn.commit()
    cur.close()
    conn.close()

    print(f"""
Listo.
  Insertados:       {inserted}
  Ya existían:      {skipped}
  Fuera Asunción:   {filtered}
  Errores:          {errors}

Para agregar fotos después:
  python scripts/download_photos.py
""")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Pobla la base de datos con lugares reales de Asunción usando OpenStreetMap (Overpass API).
No requiere API key ni billing. Las fotos quedan vacías para agregar después.

Uso (desde la raíz del proyecto):
    python scripts/populate_from_osm.py
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

DATABASE_URL = os.getenv("DATABASE_URL")

# Bounding box de Asunción: (sur, oeste, norte, este)
BBOX = "(-25.38,-57.76,-25.24,-57.52)"

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

# Tags OSM por categoría de la app
CATEGORY_FILTERS = {
    "gastronomia": {
        "amenity": ["restaurant", "cafe", "bar", "fast_food", "pub", "food_court", "ice_cream"],
        "shop":    ["bakery", "pastry"],
    },
    "hoteles": {
        "tourism": ["hotel", "motel", "hostel", "guest_house"],
    },
    "lugares": {
        "tourism": ["attraction", "museum", "gallery", "zoo", "viewpoint"],
        "amenity": ["theatre", "cinema", "arts_centre", "place_of_worship"],
        "leisure": ["park", "garden"],
        "historic": ["monument", "memorial"],
    },
}

# Mapa inverso: (tag_key, tag_value) -> categoría
TAG_TO_CATEGORY: dict[tuple[str, str], str] = {
    (key, val): cat
    for cat, groups in CATEGORY_FILTERS.items()
    for key, vals in groups.items()
    for val in vals
}


# ---------------------------------------------------------------------------
# Parsing de horarios OSM  ("Mo-Fr 09:00-18:00; Sa 09:00-13:00")
# ---------------------------------------------------------------------------

_DAYS_ORDER = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
_DAYS_ES = {
    "Mo": "lunes", "Tu": "martes", "We": "miércoles",
    "Th": "jueves", "Fr": "viernes", "Sa": "sábado", "Su": "domingo",
}


def _expand_days(spec: str) -> list[str]:
    days = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            try:
                i = _DAYS_ORDER.index(a.strip())
                j = _DAYS_ORDER.index(b.strip())
                days.extend(_DAYS_ORDER[i : j + 1])
            except ValueError:
                pass
        elif chunk in _DAYS_ORDER:
            days.append(chunk)
    return days


def parse_opening_hours(raw: str | None) -> dict | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw == "24/7":
        return {_DAYS_ES[d]: "24 horas" for d in _DAYS_ORDER}

    result = {}
    for rule in raw.split(";"):
        rule = rule.strip()
        if not rule:
            continue
        m = re.match(
            r"^((?:Mo|Tu|We|Th|Fr|Sa|Su)(?:[,\-](?:Mo|Tu|We|Th|Fr|Sa|Su))*)\s+(.+)$",
            rule,
        )
        if not m:
            continue
        days = _expand_days(m.group(1))
        time_part = m.group(2).strip()
        if time_part.lower() in ("off", "closed"):
            value = "Cerrado"
        else:
            first = time_part.split(",")[0].strip()
            value = re.sub(r"(\d{2}:\d{2})-(\d{2}:\d{2})", r"\1 - \2", first)
        for day in days:
            if day in _DAYS_ES:
                result[_DAYS_ES[day]] = value
    return result or None


# ---------------------------------------------------------------------------
# Overpass API
# ---------------------------------------------------------------------------

def _build_query() -> str:
    lines = []
    for groups in CATEGORY_FILTERS.values():
        for key, vals in groups.items():
            regex = "|".join(vals)
            for elem_type in ("node", "way"):
                lines.append(f'  {elem_type}["{key}"~"{regex}"]{BBOX};\n')
    return f"[out:json][timeout:90];\n(\n{''.join(lines)});\nout tags center;\n"


def fetch_overpass() -> list[dict]:
    query = _build_query()
    for server in OVERPASS_SERVERS:
        try:
            resp = requests.post(server, data={"data": query}, timeout=120)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            host = server.split("/")[2]
            print(f"Overpass OK ({host}): {len(elements)} elementos crudos\n")
            return elements
        except Exception as e:
            print(f"  Error con {server.split('/')[2]}: {e}")
            time.sleep(3)
    print("ERROR: ningún servidor Overpass respondió.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Clasificación y extracción
# ---------------------------------------------------------------------------

def classify(tags: dict) -> str | None:
    for key in ("amenity", "tourism", "leisure", "historic", "shop"):
        val = tags.get(key)
        if val:
            cat = TAG_TO_CATEGORY.get((key, val))
            if cat:
                return cat
    return None


def get_coords(elem: dict) -> tuple[float, float] | None:
    if elem["type"] == "node":
        lat, lon = elem.get("lat"), elem.get("lon")
    else:
        center = elem.get("center", {})
        lat, lon = center.get("lat"), center.get("lon")
    if lat is None or lon is None:
        return None
    return lat, lon


def build_address(tags: dict) -> str | None:
    parts = []
    street = tags.get("addr:street")
    number = tags.get("addr:housenumber")
    city   = tags.get("addr:city")
    if street:
        parts.append(f"{street} {number}".strip() if number else street)
    if city:
        parts.append(city)
    return ", ".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

def insert_place(cur, tags: dict, category: str, lat: float, lon: float) -> bool:
    name    = tags.get("name") or tags.get("name:es") or tags.get("name:en")
    hours   = parse_opening_hours(tags.get("opening_hours"))
    address = build_address(tags)
    cur.execute(
        """
        INSERT INTO places (
            name, category, address, phone, website,
            opening_hours, location, photos
        ) VALUES (%s, %s, %s, %s, %s, %s,
            ST_MakePoint(%s, %s)::geography, %s)
        RETURNING id
        """,
        (
            name,
            category,
            address,
            tags.get("phone") or tags.get("contact:phone"),
            tags.get("website") or tags.get("contact:website"),
            json.dumps(hours) if hours else None,
            lon, lat,
            json.dumps([]),
        ),
    )
    return cur.fetchone() is not None


def main():
    elements = fetch_overpass()

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    cur.execute("TRUNCATE route_places, places RESTART IDENTITY CASCADE")
    conn.commit()
    print("Tabla places vaciada.")

    inserted = skipped_no_name = skipped_no_cat = skipped_no_coords = 0
    seen: set[str] = set()

    for elem in elements:
        osm_key = f"{elem['type']}/{elem['id']}"
        if osm_key in seen:
            continue
        seen.add(osm_key)

        tags = elem.get("tags", {})

        name = tags.get("name") or tags.get("name:es") or tags.get("name:en")
        if not name:
            skipped_no_name += 1
            continue

        category = classify(tags)
        if not category:
            skipped_no_cat += 1
            continue

        coords = get_coords(elem)
        if not coords:
            skipped_no_coords += 1
            continue
        lat, lon = coords

        if insert_place(cur, tags, category, lat, lon):
            inserted += 1
            print(f"  ✓ [{inserted}] {name} ({category})")

    conn.commit()
    cur.close()
    conn.close()

    print(f"""
Listo.
  Insertados:                {inserted}
  Sin nombre (omitidos):     {skipped_no_name}
  Sin categoría (omitidos):  {skipped_no_cat}
  Sin coords (omitidos):     {skipped_no_coords}
""")


if __name__ == "__main__":
    main()

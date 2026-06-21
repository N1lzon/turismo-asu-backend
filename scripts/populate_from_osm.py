#!/usr/bin/env python3
"""
Pobla la base de datos con lugares reales de Asunción usando OpenStreetMap (Overpass API).
No requiere API key. Usa overpass.openstreetmap.fr como servidor principal.

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

# Bounding box de Asunción (sur, oeste, norte, este)
BBOX = "(-25.38,-57.76,-25.24,-57.55)"

OVERPASS_SERVERS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

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

TAG_TO_CATEGORY: dict[tuple[str, str], str] = {
    (key, val): cat
    for cat, groups in CATEGORY_FILTERS.items()
    for key, vals in groups.items()
    for val in vals
}

# ---------------------------------------------------------------------------
# Horarios OSM
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
                days.extend(_DAYS_ORDER[_DAYS_ORDER.index(a.strip()) : _DAYS_ORDER.index(b.strip()) + 1])
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
        m = re.match(r"^((?:Mo|Tu|We|Th|Fr|Sa|Su)(?:[,\-](?:Mo|Tu|We|Th|Fr|Sa|Su))*)\s+(.+)$", rule)
        if not m:
            continue
        time_part = m.group(2).strip()
        value = "Cerrado" if time_part.lower() in ("off", "closed") else re.sub(
            r"(\d{2}:\d{2})-(\d{2}:\d{2})", r"\1 - \2", time_part.split(",")[0].strip()
        )
        for day in _expand_days(m.group(1)):
            if day in _DAYS_ES:
                result[_DAYS_ES[day]] = value
    return result or None


# ---------------------------------------------------------------------------
# Overpass API — una query por tag key
# ---------------------------------------------------------------------------

def _build_queries() -> list[tuple[str, str]]:
    merged: dict[str, set[str]] = {}
    for groups in CATEGORY_FILTERS.values():
        for key, vals in groups.items():
            merged.setdefault(key, set()).update(vals)

    queries = []
    for key, vals in merged.items():
        regex = "|".join(sorted(vals))
        q = (
            f'[out:json][timeout:30];\n'
            f'(\n'
            f'  node["{key}"~"{regex}"]{BBOX};\n'
            f'  way["{key}"~"{regex}"]{BBOX};\n'
            f');\n'
            f'out tags center;\n'
        )
        queries.append((key, q))
    return queries


def _run_query(query: str) -> list[dict] | None:
    for server in OVERPASS_SERVERS:
        try:
            resp = requests.post(server, data={"data": query}, timeout=45)
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as e:
            print(f"    Error ({server.split('/')[2]}): {e}")
            time.sleep(2)
    return None


def fetch_all() -> list[dict]:
    queries = _build_queries()
    all_elements: list[dict] = []
    print(f"Consultando Overpass API ({len(queries)} queries)...\n")
    for i, (tag_key, query) in enumerate(queries, 1):
        print(f"  [{i}/{len(queries)}] {tag_key}...", end=" ", flush=True)
        elements = _run_query(query)
        if elements is None:
            print("FALLÓ")
        else:
            print(f"{len(elements)} elementos")
            all_elements.extend(elements)
        time.sleep(1)
    print(f"\nTotal: {len(all_elements)} elementos crudos\n")
    return all_elements


# ---------------------------------------------------------------------------
# Clasificación
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
        return elem.get("lat"), elem.get("lon")
    center = elem.get("center", {})
    return center.get("lat"), center.get("lon")


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
    hours = parse_opening_hours(tags.get("opening_hours"))
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
            tags.get("name") or tags.get("name:es") or tags.get("name:en"),
            category,
            build_address(tags),
            tags.get("phone") or tags.get("contact:phone"),
            tags.get("website") or tags.get("contact:website"),
            json.dumps(hours) if hours else None,
            lon, lat,
            json.dumps([]),
        ),
    )
    return cur.fetchone() is not None


def main():
    elements = fetch_all()

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()
    cur.execute("TRUNCATE route_places, places RESTART IDENTITY CASCADE")
    conn.commit()
    print("Tabla places vaciada.\n")

    inserted = skipped = 0
    seen: set[str] = set()

    for elem in elements:
        osm_key = f"{elem['type']}/{elem['id']}"
        if osm_key in seen:
            continue
        seen.add(osm_key)

        tags = elem.get("tags", {})
        name = tags.get("name") or tags.get("name:es") or tags.get("name:en")
        if not name:
            skipped += 1
            continue

        category = classify(tags)
        if not category:
            skipped += 1
            continue

        coords = get_coords(elem)
        if not coords or None in coords:
            skipped += 1
            continue

        lat, lon = coords
        if insert_place(cur, tags, category, lat, lon):
            inserted += 1
            print(f"  ✓ [{inserted}] {name} ({category})")

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nListo. Insertados: {inserted} | Omitidos (sin nombre/cat/coords): {skipped}")
    print("(Fotos vacías — agregar después con un script dedicado)")


if __name__ == "__main__":
    main()

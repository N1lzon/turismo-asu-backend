#!/usr/bin/env python3
"""
Pobla la base de datos con lugares reales de Asunción usando datos de OpenStreetMap.
Descarga el extract de Paraguay de Geofabrik (~15 MB) y lo procesa localmente,
sin depender de servidores Overpass públicos.

Requiere: pip install pyosmium

Uso (desde la raíz del proyecto):
    python scripts/populate_from_osm.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import osmium
import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Bounding box de Asunción (sur, oeste, norte, este)
BBOX_MIN_LAT, BBOX_MIN_LON = -25.38, -57.76
BBOX_MAX_LAT, BBOX_MAX_LON = -25.24, -57.52

# Archivo local del extract de Paraguay (se guarda para no volver a descargar)
PBF_PATH = Path("/tmp/paraguay-latest.osm.pbf")
PBF_URL  = "https://download.geofabrik.de/south-america/paraguay-latest.osm.pbf"

# Tags OSM por categoría de la app
CATEGORY_FILTERS = {
    "gastronomia": {
        "amenity": {"restaurant", "cafe", "bar", "fast_food", "pub", "food_court", "ice_cream"},
        "shop":    {"bakery", "pastry"},
    },
    "hoteles": {
        "tourism": {"hotel", "motel", "hostel", "guest_house"},
    },
    "lugares": {
        "tourism": {"attraction", "museum", "gallery", "zoo", "viewpoint"},
        "amenity": {"theatre", "cinema", "arts_centre", "place_of_worship"},
        "leisure": {"park", "garden"},
        "historic": {"monument", "memorial"},
    },
}

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
# Descarga del extract de Paraguay
# ---------------------------------------------------------------------------

def download_pbf():
    if PBF_PATH.exists():
        size_mb = PBF_PATH.stat().st_size / 1_000_000
        print(f"Extract ya descargado: {PBF_PATH} ({size_mb:.1f} MB)\n")
        return

    print(f"Descargando extract de Paraguay desde Geofabrik (~15 MB)...")
    resp = requests.get(PBF_URL, stream=True, timeout=120)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    downloaded = 0
    with open(PBF_PATH, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
            downloaded += len(chunk)
            if total:
                pct = downloaded * 100 // total
                print(f"\r  {pct}% ({downloaded // 1_000_000} MB)", end="", flush=True)
    print(f"\nDescarga completa: {PBF_PATH}\n")


# ---------------------------------------------------------------------------
# Procesamiento del archivo OSM con pyosmium
# ---------------------------------------------------------------------------

class AsuncionHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.places: list[dict] = []
        self._seen: set[str] = set()

    def _in_bbox(self, lat: float, lon: float) -> bool:
        return (BBOX_MIN_LAT <= lat <= BBOX_MAX_LAT and
                BBOX_MIN_LON <= lon <= BBOX_MAX_LON)

    def _classify(self, tags: dict) -> str | None:
        for key in ("amenity", "tourism", "leisure", "historic", "shop"):
            val = tags.get(key)
            if val:
                cat = TAG_TO_CATEGORY.get((key, val))
                if cat:
                    return cat
        return None

    def _add(self, osm_key: str, tags: dict, lat: float, lon: float):
        if osm_key in self._seen:
            return
        self._seen.add(osm_key)

        name = tags.get("name") or tags.get("name:es") or tags.get("name:en")
        if not name:
            return

        category = self._classify(tags)
        if not category:
            return

        if not self._in_bbox(lat, lon):
            return

        self.places.append({
            "name":     name,
            "category": category,
            "lat":      lat,
            "lon":      lon,
            "address":  self._build_address(tags),
            "phone":    tags.get("phone") or tags.get("contact:phone"),
            "website":  tags.get("website") or tags.get("contact:website"),
            "opening_hours": parse_opening_hours(tags.get("opening_hours")),
        })

    def _build_address(self, tags: dict) -> str | None:
        parts = []
        street = tags.get("addr:street")
        number = tags.get("addr:housenumber")
        city   = tags.get("addr:city")
        if street:
            parts.append(f"{street} {number}".strip() if number else street)
        if city:
            parts.append(city)
        return ", ".join(parts) if parts else None

    def node(self, n):
        if not n.location.valid():
            return
        self._add(f"n{n.id}", dict(n.tags), n.location.lat, n.location.lon)

    def way(self, w):
        try:
            lats, lons = [], []
            for node in w.nodes:
                if node.location.valid():
                    lats.append(node.location.lat)
                    lons.append(node.location.lon)
            if not lats:
                return
            lat = sum(lats) / len(lats)
            lon = sum(lons) / len(lons)
            self._add(f"w{w.id}", dict(w.tags), lat, lon)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

def insert_place(cur, place: dict) -> bool:
    hours = place["opening_hours"]
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
            place["name"],
            place["category"],
            place["address"],
            place["phone"],
            place["website"],
            json.dumps(hours) if hours else None,
            place["lon"], place["lat"],
            json.dumps([]),
        ),
    )
    return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    download_pbf()

    print(f"Leyendo {PBF_PATH} y filtrando Asunción...")
    t0 = time.time()
    handler = AsuncionHandler()
    handler.apply_file(str(PBF_PATH), locations=True)
    elapsed = time.time() - t0
    print(f"  {len(handler.places)} lugares encontrados en {elapsed:.1f}s\n")

    if not handler.places:
        print("No se encontraron lugares. Verificá el bounding box.")
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()

    cur.execute("TRUNCATE route_places, places RESTART IDENTITY CASCADE")
    conn.commit()
    print("Tabla places vaciada.")

    inserted = 0
    for place in handler.places:
        if insert_place(cur, place):
            inserted += 1
            print(f"  ✓ [{inserted}] {place['name']} ({place['category']})")

    conn.commit()
    cur.close()
    conn.close()

    print(f"""
Listo.
  Insertados: {inserted}
  (Fotos vacías — agregar después con un script dedicado)
""")


if __name__ == "__main__":
    main()

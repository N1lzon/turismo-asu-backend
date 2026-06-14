#!/usr/bin/env python3
"""
Pobla la base de datos con lugares reales de Asunción usando datos de OpenStreetMap.
Descarga el extract de Paraguay de Geofabrik (~50 MB) y lo procesa localmente
con stdlib pura (bz2 + xml.etree). Sin dependencias extra.

Uso (desde la raíz del proyecto):
    python scripts/populate_from_osm.py
"""

import bz2
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Bounding box de Asunción (sur, oeste, norte, este)
BBOX_MIN_LAT, BBOX_MIN_LON = -25.38, -57.76
BBOX_MAX_LAT, BBOX_MAX_LON = -25.24, -57.52

# Bbox extendida para almacenar coords de nodos de ways que cruzan el borde
NODE_BBOX_MIN_LAT, NODE_BBOX_MIN_LON = -25.50, -57.90
NODE_BBOX_MAX_LAT, NODE_BBOX_MAX_LON = -25.10, -57.40

OSM_PATH = Path("/tmp/paraguay-latest.osm.bz2")
OSM_URL  = "https://download.geofabrik.de/south-america/paraguay-latest.osm.bz2"

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
# Descarga
# ---------------------------------------------------------------------------

def download_osm():
    if OSM_PATH.exists():
        mb = OSM_PATH.stat().st_size / 1_000_000
        print(f"Extract ya descargado: {OSM_PATH} ({mb:.0f} MB)\n")
        return
    print(f"Descargando extract de Paraguay desde Geofabrik (~50 MB)...")
    resp = requests.get(OSM_URL, stream=True, timeout=300)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    done = 0
    with open(OSM_PATH, "wb") as f:
        for chunk in resp.iter_content(65536):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done * 100 // total}%  ({done // 1_000_000} MB)", end="", flush=True)
    print(f"\nDescarga completa.\n")


# ---------------------------------------------------------------------------
# Parseo OSM XML (single-pass)
# ---------------------------------------------------------------------------

def _classify(tags: dict) -> str | None:
    for key in ("amenity", "tourism", "leisure", "historic", "shop"):
        val = tags.get(key)
        if val:
            cat = TAG_TO_CATEGORY.get((key, val))
            if cat:
                return cat
    return None


def _build_address(tags: dict) -> str | None:
    parts = []
    street = tags.get("addr:street")
    number = tags.get("addr:housenumber")
    city   = tags.get("addr:city")
    if street:
        parts.append(f"{street} {number}".strip() if number else street)
    if city:
        parts.append(city)
    return ", ".join(parts) if parts else None


def _in_asuncion(lat: float, lon: float) -> bool:
    return BBOX_MIN_LAT <= lat <= BBOX_MAX_LAT and BBOX_MIN_LON <= lon <= BBOX_MAX_LON


def _in_extended(lat: float, lon: float) -> bool:
    return NODE_BBOX_MIN_LAT <= lat <= NODE_BBOX_MAX_LAT and NODE_BBOX_MIN_LON <= lon <= NODE_BBOX_MAX_LON


def parse_osm() -> list[dict]:
    """
    Parseo de un solo paso sobre el XML comprimido.
    Los nodos siempre vienen antes que los ways en OSM XML,
    así que guardamos coords de nodos y las usamos al procesar ways.
    """
    node_coords: dict[str, tuple[float, float]] = {}
    places: list[dict] = []
    seen: set[str] = set()

    # Estado del elemento actual
    cur_type  = None   # "node" | "way"
    cur_id    = None
    cur_lat   = None
    cur_lon   = None
    cur_tags  : dict  = {}
    cur_refs  : list  = []

    def _flush(etype: str):
        nonlocal cur_type, cur_id, cur_lat, cur_lon, cur_tags, cur_refs
        key = f"{etype}/{cur_id}"
        if key in seen:
            return

        if etype == "node" and cur_lat is not None:
            if _in_extended(cur_lat, cur_lon):
                node_coords[cur_id] = (cur_lat, cur_lon)
            if _in_asuncion(cur_lat, cur_lon) and cur_tags:
                name = cur_tags.get("name") or cur_tags.get("name:es") or cur_tags.get("name:en")
                cat  = _classify(cur_tags)
                if name and cat:
                    seen.add(key)
                    places.append({
                        "name": name, "category": cat,
                        "lat": cur_lat, "lon": cur_lon,
                        "address": _build_address(cur_tags),
                        "phone":   cur_tags.get("phone") or cur_tags.get("contact:phone"),
                        "website": cur_tags.get("website") or cur_tags.get("contact:website"),
                        "opening_hours": parse_opening_hours(cur_tags.get("opening_hours")),
                    })

        elif etype == "way" and cur_refs and cur_tags:
            name = cur_tags.get("name") or cur_tags.get("name:es") or cur_tags.get("name:en")
            cat  = _classify(cur_tags)
            if name and cat:
                lats = [node_coords[r][0] for r in cur_refs if r in node_coords]
                lons = [node_coords[r][1] for r in cur_refs if r in node_coords]
                if lats:
                    lat = sum(lats) / len(lats)
                    lon = sum(lons) / len(lons)
                    if _in_asuncion(lat, lon):
                        seen.add(key)
                        places.append({
                            "name": name, "category": cat,
                            "lat": lat, "lon": lon,
                            "address": _build_address(cur_tags),
                            "phone":   cur_tags.get("phone") or cur_tags.get("contact:phone"),
                            "website": cur_tags.get("website") or cur_tags.get("contact:website"),
                            "opening_hours": parse_opening_hours(cur_tags.get("opening_hours")),
                        })

        cur_type = None; cur_id = None; cur_lat = None; cur_lon = None
        cur_tags = {}; cur_refs = []

    print(f"Parseando {OSM_PATH} (esto puede tardar 1-2 minutos)...")
    t0 = time.time()

    with bz2.open(OSM_PATH, "rb") as f:
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                if elem.tag == "node":
                    cur_type = "node"
                    cur_id   = elem.get("id")
                    lat = elem.get("lat")
                    lon = elem.get("lon")
                    cur_lat = float(lat) if lat else None
                    cur_lon = float(lon) if lon else None
                    cur_tags = {}
                elif elem.tag == "way":
                    cur_type = "way"
                    cur_id   = elem.get("id")
                    cur_tags = {}
                    cur_refs = []

            elif event == "end":
                if elem.tag == "tag" and cur_type:
                    cur_tags[elem.get("k")] = elem.get("v")
                elif elem.tag == "nd" and cur_type == "way":
                    cur_refs.append(elem.get("ref"))
                elif elem.tag in ("node", "way") and cur_type == elem.tag:
                    _flush(elem.tag)
                elem.clear()

    elapsed = time.time() - t0
    print(f"  {len(places)} lugares en Asunción encontrados ({elapsed:.0f}s)\n")
    return places


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

def insert_place(cur, p: dict) -> bool:
    hours = p["opening_hours"]
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
            p["name"], p["category"], p["address"],
            p["phone"], p["website"],
            json.dumps(hours) if hours else None,
            p["lon"], p["lat"],
            json.dumps([]),
        ),
    )
    return cur.fetchone() is not None


def main():
    download_osm()
    places = parse_osm()

    if not places:
        print("No se encontraron lugares. Revisá el bounding box.")
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    cur  = conn.cursor()
    cur.execute("TRUNCATE route_places, places RESTART IDENTITY CASCADE")
    conn.commit()
    print("Tabla places vaciada.\n")

    inserted = 0
    for p in places:
        if insert_place(cur, p):
            inserted += 1
            print(f"  ✓ [{inserted}] {p['name']} ({p['category']})")

    conn.commit()
    cur.close()
    conn.close()

    print(f"\nListo. Insertados: {inserted}")
    print("(Fotos vacías — agregar después con un script dedicado)")


if __name__ == "__main__":
    main()

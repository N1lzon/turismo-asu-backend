"""
Populates route_places for the 3 preset routes using place IDs
already in the production DB (imported from OpenStreetMap).

Run once:
  cd turismo-asu-backend
  python scripts/seed_route_places.py

Requires DATABASE_URL in the environment or a .env file.
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

# Route IDs in production (confirmed via GET /routes/presets)
ROUTE_CENTRO_HISTORICO = 14
ROUTE_NATURALEZA = 15
ROUTE_GASTRONOMIA = 16

# Place IDs confirmed via GET /places/search and GET /places/nearby
# Centro Histórico: Panteón → Casa Independencia → Museo Barro → Museo Cabildo
# (Mercado 4 is absent from the DB; Museo del Cabildo is a nearby historic landmark)
ROUTE_PLACES = {
    ROUTE_CENTRO_HISTORICO: [1624, 1176, 1375, 1177],
    ROUTE_NATURALEZA:        [1275, 1422, 553],
    ROUTE_GASTRONOMIA:       [369, 553, 801],
}


def main():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    # Verify place IDs exist before inserting
    all_ids = [pid for ids in ROUTE_PLACES.values() for pid in ids]
    cur.execute("SELECT id, name FROM places WHERE id = ANY(%s)", (all_ids,))
    found = {row[0]: row[1] for row in cur.fetchall()}
    missing = [pid for pid in all_ids if pid not in found]
    if missing:
        print(f"ERROR: place IDs not found in DB: {missing}")
        conn.close()
        return

    print("Places found:")
    for pid, name in found.items():
        print(f"  {pid}: {name}")

    # Clear existing route_places for these routes only
    cur.execute(
        "DELETE FROM route_places WHERE route_id = ANY(%s)",
        ([ROUTE_CENTRO_HISTORICO, ROUTE_NATURALEZA, ROUTE_GASTRONOMIA],)
    )
    deleted = cur.rowcount
    if deleted:
        print(f"\nCleared {deleted} existing route_places rows")

    # Insert
    total = 0
    for route_id, place_ids in ROUTE_PLACES.items():
        for order_index, place_id in enumerate(place_ids):
            cur.execute(
                "INSERT INTO route_places (route_id, place_id, order_index) VALUES (%s, %s, %s)",
                (route_id, place_id, order_index)
            )
            total += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"\n✓ Inserted {total} route_places rows")
    print("Done. Verify with: GET /routes/presets")


if __name__ == "__main__":
    main()

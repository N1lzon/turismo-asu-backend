from fastapi import APIRouter, HTTPException, Query
from app.database.connection import get_connection

router = APIRouter(prefix="/places", tags=["places"])

@router.get("/nearby")
def get_nearby_places(
    lat: float = Query(..., description="Latitud del usuario"),
    lng: float = Query(..., description="Longitud del usuario"),
    radius: int = Query(2000, description="Radio en metros"),
    category: str = Query(None, description="Filtrar por categoría")
):
    conn = get_connection()
    cur = conn.cursor()

    query = """
        SELECT
            id, name, category, address, phone, website,
            rating, total_ratings, opening_hours, photos,
            ST_Y(location::geometry) AS lat,
            ST_X(location::geometry) AS lng,
            ST_Distance(location, ST_MakePoint(%s, %s)::geography) AS distance_meters
        FROM places
        WHERE ST_DWithin(location, ST_MakePoint(%s, %s)::geography, %s)
        {category_filter}
        ORDER BY distance_meters
    """

    params = [lng, lat, lng, lat, radius]

    if category:
        query = query.format(category_filter="AND category = %s")
        params.append(category)
    else:
        query = query.format(category_filter="")

    cur.execute(query, params)
    places = cur.fetchall()

    cur.close()
    conn.close()

    return [dict(p) for p in places]

@router.get("/search")
def search_places(
    q: str = Query(..., description="Nombre del lugar a buscar", min_length=2),
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id, name, category, address, rating, photos,
            ST_Y(location::geometry) AS lat,
            ST_X(location::geometry) AS lng
        FROM places
        WHERE name ILIKE %s
        ORDER BY name
    """, (f"%{q}%",))

    places = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(p) for p in places]


@router.get("/{place_id}")
def get_place(place_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id, name, category, address, phone, website,
            rating, total_ratings, opening_hours, photos,
            ST_Y(location::geometry) AS lat,
            ST_X(location::geometry) AS lng
        FROM places
        WHERE id = %s
    """, (place_id,))

    place = cur.fetchone()
    cur.close()
    conn.close()

    if not place:
        raise HTTPException(status_code=404, detail="Lugar no encontrado")

    return dict(place)


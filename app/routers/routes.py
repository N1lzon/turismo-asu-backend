from fastapi import APIRouter, HTTPException
from app.database.connection import get_connection

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("/presets")
def get_preset_routes():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            r.id,
            r.name,
            r.description,
            COUNT(rp.place_id) AS total_places
        FROM routes r
        LEFT JOIN route_places rp ON r.id = rp.route_id
        WHERE r.is_preset = TRUE
        GROUP BY r.id
        ORDER BY r.id
    """)

    routes = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(r) for r in routes]


@router.get("/presets/{route_id}")
def get_preset_route(route_id: int):
    conn = get_connection()
    cur = conn.cursor()

    # Verificar que la ruta existe y es predeterminada
    cur.execute("""
        SELECT id, name, description
        FROM routes
        WHERE id = %s AND is_preset = TRUE
    """, (route_id,))

    route = cur.fetchone()

    if not route:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    # Obtener los lugares de la ruta en orden
    cur.execute("""
        SELECT
            p.id,
            p.name,
            p.category,
            p.address,
            p.rating,
            p.photos,
            p.opening_hours,
            ST_Y(p.location::geometry) AS lat,
            ST_X(p.location::geometry) AS lng,
            rp.order_index
        FROM route_places rp
        JOIN places p ON rp.place_id = p.id
        WHERE rp.route_id = %s
        ORDER BY rp.order_index
    """, (route_id,))

    places = cur.fetchall()
    cur.close()
    conn.close()

    return {
        **dict(route),
        "places": [dict(p) for p in places]
    }
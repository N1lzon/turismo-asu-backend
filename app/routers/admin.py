import os
import uuid
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Any
from fastapi import APIRouter, Body, HTTPException, Depends, status, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from jose import jwt
from app.database.connection import get_connection
from app.dependencies import verify_jwt

router = APIRouter(prefix="/admin", tags=["admin"])

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 8
_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_PHOTOS_DIR = Path("static/photos")
_VALID_CATEGORIES = {"gastronomia", "hoteles", "lugares"}

_PLACE_SELECT = """
    SELECT
        id, name, category, address, phone, website,
        rating, total_ratings, opening_hours, photos,
        ST_Y(location::geometry) AS lat,
        ST_X(location::geometry) AS lng,
        created_at
    FROM places
"""


@router.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends()):
    expected_user = os.getenv("ADMIN_USERNAME")
    expected_pass = os.getenv("ADMIN_PASSWORD")

    if form.username != expected_user or form.password != expected_pass:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )

    payload = {
        "sub": form.username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=_TOKEN_EXPIRE_HOURS),
    }
    token = jwt.encode(payload, os.getenv("JWT_SECRET"), algorithm=_ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/places", dependencies=[Depends(verify_jwt)])
def list_places():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(_PLACE_SELECT + "ORDER BY name")
    places = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(p) for p in places]


@router.get("/places/{place_id}", dependencies=[Depends(verify_jwt)])
def get_place(place_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(_PLACE_SELECT + "WHERE id = %s", (place_id,))
    place = cur.fetchone()
    cur.close()
    conn.close()
    if not place:
        raise HTTPException(status_code=404, detail="Lugar no encontrado")
    return dict(place)


class PlaceUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    rating: Optional[float] = None
    total_ratings: Optional[int] = None
    opening_hours: Optional[Any] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


@router.put("/places/{place_id}", dependencies=[Depends(verify_jwt)])
def update_place(place_id: int, body: PlaceUpdate):
    if body.category is not None and body.category not in _VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Categoría inválida. Valores: {_VALID_CATEGORIES}")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM places WHERE id = %s", (place_id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Lugar no encontrado")

    set_parts = []
    params = []

    for field in ("name", "category", "address", "phone", "website", "rating", "total_ratings"):
        val = getattr(body, field)
        if val is not None:
            set_parts.append(f"{field} = %s")
            params.append(val)

    if body.opening_hours is not None:
        set_parts.append("opening_hours = %s::jsonb")
        params.append(json.dumps(body.opening_hours))

    if body.lat is not None and body.lng is not None:
        set_parts.append("location = ST_MakePoint(%s, %s)::geography")
        params.extend([body.lng, body.lat])

    if not set_parts:
        cur.close()
        conn.close()
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")

    params.append(place_id)
    cur.execute(f"UPDATE places SET {', '.join(set_parts)} WHERE id = %s", params)
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}


@router.post("/places/{place_id}/photos", dependencies=[Depends(verify_jwt)])
async def upload_photo(place_id: int, file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Formato no permitido. Usar: jpg, jpeg, png, webp")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM places WHERE id = %s", (place_id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Lugar no encontrado")

    _PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{place_id}_{uuid.uuid4().hex}{ext}"
    filepath = _PHOTOS_DIR / filename
    filepath.write_bytes(await file.read())

    base_url = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
    photo_url = f"{base_url}/static/photos/{filename}"

    cur.execute(
        "UPDATE places SET photos = photos || jsonb_build_array(%s) WHERE id = %s",
        (photo_url, place_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"url": photo_url}


class PhotoDelete(BaseModel):
    url: str


@router.delete("/places/{place_id}/photos", dependencies=[Depends(verify_jwt)])
def delete_photo(place_id: int, body: PhotoDelete):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE places
        SET photos = (
            SELECT COALESCE(jsonb_agg(elem), '[]'::jsonb)
            FROM jsonb_array_elements(photos) elem
            WHERE elem <> to_jsonb(%s::text)
        )
        WHERE id = %s
    """, (body.url, place_id))
    conn.commit()
    cur.close()
    conn.close()

    filepath = _PHOTOS_DIR / Path(body.url).name
    if filepath.exists():
        filepath.unlink()

    return {"ok": True}


class RouteCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_preset: bool = False
    start_time: Optional[str] = None
    place_ids: list[int] = []


@router.post("/routes", dependencies=[Depends(verify_jwt)], status_code=201)
def create_route(body: RouteCreate):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO routes (name, description, is_preset, start_time) VALUES (%s, %s, %s, %s) RETURNING id",
        (body.name, body.description, body.is_preset, body.start_time),
    )
    route_id = cur.fetchone()["id"]

    for order_index, place_id in enumerate(body.place_ids):
        cur.execute(
            "INSERT INTO route_places (route_id, place_id, order_index) VALUES (%s, %s, %s)",
            (route_id, place_id, order_index),
        )

    conn.commit()
    cur.close()
    conn.close()
    return {"id": route_id}


@router.get("/routes", dependencies=[Depends(verify_jwt)])
def list_routes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            r.id, r.name, r.description, r.is_preset, r.start_time,
            COALESCE(
                json_agg(
                    json_build_object('id', p.id, 'name', p.name, 'category', p.category)
                    ORDER BY rp.order_index
                ) FILTER (WHERE p.id IS NOT NULL),
                '[]'::json
            ) AS places
        FROM routes r
        LEFT JOIN route_places rp ON r.id = rp.route_id
        LEFT JOIN places p ON rp.place_id = p.id
        GROUP BY r.id
        ORDER BY r.name
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


@router.get("/routes/{route_id}", dependencies=[Depends(verify_jwt)])
def get_route(route_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            r.id, r.name, r.description, r.is_preset, r.start_time,
            COALESCE(
                json_agg(
                    json_build_object('id', p.id, 'name', p.name, 'category', p.category)
                    ORDER BY rp.order_index
                ) FILTER (WHERE p.id IS NOT NULL),
                '[]'::json
            ) AS places
        FROM routes r
        LEFT JOIN route_places rp ON r.id = rp.route_id
        LEFT JOIN places p ON rp.place_id = p.id
        WHERE r.id = %s
        GROUP BY r.id
    """, (route_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    return dict(row)


class RouteUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    place_ids: Optional[list[int]] = None


@router.put("/routes/{route_id}", dependencies=[Depends(verify_jwt)])
def update_route(route_id: int, body: RouteUpdate):
    set_parts = []
    params = []

    if body.name is not None:
        if not body.name.strip():
            raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
        set_parts.append("name = %s")
        params.append(body.name)

    if body.description is not None:
        set_parts.append("description = %s")
        params.append(body.description)

    if not set_parts and body.place_ids is None:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM routes WHERE id = %s", (route_id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    if set_parts:
        params.append(route_id)
        cur.execute(f"UPDATE routes SET {', '.join(set_parts)} WHERE id = %s", params)

    if body.place_ids is not None:
        cur.execute("DELETE FROM route_places WHERE route_id = %s", (route_id,))
        for order_index, place_id in enumerate(body.place_ids):
            cur.execute(
                "INSERT INTO route_places (route_id, place_id, order_index) VALUES (%s, %s, %s)",
                (route_id, place_id, order_index),
            )

    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}


@router.delete("/routes/{route_id}", dependencies=[Depends(verify_jwt)])
def delete_route(route_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM routes WHERE id = %s", (route_id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    cur.execute("DELETE FROM routes WHERE id = %s", (route_id,))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}


@router.get("/metrics", dependencies=[Depends(verify_jwt)])
def get_metrics():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT data FROM metrics WHERE id = 1")
    row = cur.fetchone()
    data = row["data"] if row else {}
    if isinstance(data, str):
        data = json.loads(data)

    cur.execute("SELECT COUNT(*) AS total FROM places")
    total = cur.fetchone()["total"]

    cur.execute("SELECT category, COUNT(*) AS count FROM places GROUP BY category")
    por_categoria = {r["category"]: r["count"] for r in cur.fetchall()}

    cur.execute("SELECT COUNT(*) AS count FROM places WHERE photos = '[]'::jsonb")
    sin_fotos = cur.fetchone()["count"]

    cur.execute("SELECT COALESCE(SUM(jsonb_array_length(photos)), 0) AS total FROM places")
    total_fotos = cur.fetchone()["total"]

    cur.close()
    conn.close()

    lugares_data = dict(data.get("lugares", {}))
    lugares_data.update({
        "total": total,
        "por_categoria": por_categoria,
        "sin_fotos": sin_fotos,
        "total_fotos": total_fotos,
    })

    return {**data, "lugares": lugares_data}


@router.put("/metrics", dependencies=[Depends(verify_jwt)])
def update_metrics(body: Any = Body(...)):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE metrics SET data = %s WHERE id = 1", (json.dumps(body),))
    conn.commit()
    cur.close()
    conn.close()
    return {"ok": True}


@router.delete("/places/{place_id}", dependencies=[Depends(verify_jwt)])
def delete_place(place_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT photos FROM places WHERE id = %s", (place_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Lugar no encontrado")

    cur.execute("DELETE FROM places WHERE id = %s", (place_id,))
    conn.commit()
    cur.close()
    conn.close()

    for url in (row["photos"] or []):
        filepath = _PHOTOS_DIR / Path(url).name
        if filepath.exists():
            filepath.unlink()

    return {"ok": True}

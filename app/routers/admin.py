import os
import uuid
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Any
from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File
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

import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from app.database.connection import get_connection
from app.dependencies import verify_jwt

router = APIRouter(prefix="/admin", tags=["admin"])

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 8


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

    cur.execute("""
        SELECT
            id, name, category, address, phone, website,
            rating, total_ratings, opening_hours, photos,
            ST_Y(location::geometry) AS lat,
            ST_X(location::geometry) AS lng,
            created_at
        FROM places
        ORDER BY name
    """)

    places = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(p) for p in places]

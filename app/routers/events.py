from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.database.connection import get_connection

router = APIRouter(prefix="/events", tags=["events"])


class EventCreate(BaseModel):
    name: str
    description: Optional[str] = None
    photo: Optional[str] = None
    date: str          # formato: YYYY-MM-DD
    start_time: str    # formato: HH:MM
    end_time: Optional[str] = None
    address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


@router.get("")
def get_events():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id, name, description, photo, date, start_time, end_time, address,
            ST_Y(location::geometry) AS lat,
            ST_X(location::geometry) AS lng
        FROM events
        WHERE location IS NOT NULL
        UNION ALL
        SELECT
            id, name, description, photo, date, start_time, end_time, address,
            NULL AS lat,
            NULL AS lng
        FROM events
        WHERE location IS NULL
        ORDER BY date, start_time
    """)

    events = cur.fetchall()
    cur.close()
    conn.close()

    return [dict(e) for e in events]


@router.get("/{event_id}")
def get_event(event_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id, name, description, photo, date, start_time, end_time, address,
            ST_Y(location::geometry) AS lat,
            ST_X(location::geometry) AS lng
        FROM events
        WHERE id = %s
    """, (event_id,))

    event = cur.fetchone()
    cur.close()
    conn.close()

    if not event:
        raise HTTPException(status_code=404, detail="Evento no encontrado")

    return dict(event)


@router.post("", status_code=201)
def create_event(event: EventCreate):
    conn = get_connection()
    cur = conn.cursor()

    location = None
    if event.lat is not None and event.lng is not None:
        location = f"ST_MakePoint({event.lng}, {event.lat})::geography"

    if location:
        cur.execute("""
            INSERT INTO events (name, description, photo, date, start_time, end_time, address, location)
            VALUES (%s, %s, %s, %s, %s, %s, %s, ST_MakePoint(%s, %s)::geography)
            RETURNING id
        """, (
            event.name, event.description, event.photo,
            event.date, event.start_time, event.end_time,
            event.address, event.lng, event.lat
        ))
    else:
        cur.execute("""
            INSERT INTO events (name, description, photo, date, start_time, end_time, address)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            event.name, event.description, event.photo,
            event.date, event.start_time, event.end_time,
            event.address
        ))

    new_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()

    return {"id": new_id}


@router.delete("/{event_id}", status_code=204)
def delete_event(event_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM events WHERE id = %s RETURNING id", (event_id,))
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if not deleted:
        raise HTTPException(status_code=404, detail="Evento no encontrado")

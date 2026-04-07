# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

REST API backend for a tourism mobile app focused on Asunción, Paraguay. Built with **FastAPI + PostgreSQL + PostGIS**. No ORM — all queries use raw SQL via `psycopg2`.

## Running the server

```bash
uvicorn app.main:app --reload
```

Interactive API docs available at `http://localhost:8000/docs`.

## Database setup

```bash
# Create tables (requires PostgreSQL + PostGIS extension)
psql -d turismo_asu -f scripts/create_tables.sql

# Seed with test data
python scripts/seed_data.py
```

The `.env` file must contain `DATABASE_URL` (PostgreSQL connection string) and optionally `GOOGLE_PLACES_API_KEY`.

## Architecture

- **`app/main.py`** — FastAPI app setup, CORS middleware, router registration
- **`app/database/connection.py`** — Single `get_connection()` function returning a `psycopg2` connection with `RealDictCursor` (rows come back as dicts)
- **`app/routers/places.py`** — `/places` endpoints using PostGIS for geospatial queries
- **`app/routers/routes.py`** — `/routes` endpoints for preset tourist routes

## Database schema

Three tables:
- **`places`** — tourist POIs with a `GEOGRAPHY(POINT, 4326)` column called `location` (indexed with GIST)
- **`routes`** — named tourist routes (`is_preset = TRUE` for app-defined routes)
- **`route_places`** — join table linking routes to places with an `order_index`

## Key patterns

**Geospatial queries:** The `location` column stores coordinates as PostGIS geography. To extract lat/lng in SQL use `ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng`. Distance queries use `ST_DWithin` and `ST_Distance` with `ST_MakePoint(lng, lat)::geography` — note longitude comes first in `ST_MakePoint`.

**Connection handling:** Each endpoint opens and closes its own connection. No connection pooling currently.

**User-created routes are not stored in the backend** — they live on the mobile device using AsyncStorage.

## Place categories

Valid values for the `category` field: `restaurant`, `museum`, `park`, `hotel`, `bar`, `attraction`

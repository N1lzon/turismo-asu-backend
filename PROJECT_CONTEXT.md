# Contexto del Proyecto — Turismo Asunción

## Descripción general

App móvil de turismo para Asunción, Paraguay. El proyecto tiene dos partes:
- **Backend:** `/turismo-asu-backend` — FastAPI + PostgreSQL + PostGIS
- **Frontend:** por crear — React Native + Expo

---

## Backend

**Stack:** FastAPI, PostgreSQL, PostGIS, psycopg2 (sin ORM, SQL crudo)

**Correr el servidor:**
```bash
uvicorn app.main:app --reload
# Docs en http://localhost:8000/docs
```

**Estructura:**
```
app/
├── main.py                  # FastAPI app, CORS, registro de routers
├── routers/
│   ├── places.py            # /places — lugares turísticos
│   ├── routes.py            # /routes — rutas predeterminadas
│   └── events.py            # /events — eventos
└── database/
    └── connection.py        # get_connection() con RealDictCursor
```

### Base de datos

Tabla `places` — POIs turísticos con columna `location GEOGRAPHY(POINT, 4326)` (PostGIS).
Categorías válidas: `restaurant`, `museum`, `park`, `hotel`, `bar`, `attraction`

Tabla `routes` + `route_places` — rutas predeterminadas con lugares ordenados (`order_index`).

Tabla `events` — eventos con `date DATE`, `start_time TIME`, `end_time TIME`, `photo TEXT`, `location GEOGRAPHY`.

### Endpoints

**Lugares `/places`**
- `GET /places/nearby?lat=&lng=&radius=2000&category=` — cercanos por distancia (PostGIS)
- `GET /places/search?q=` — búsqueda por nombre
- `GET /places/{id}` — detalle

**Rutas `/routes`**
- `GET /routes/presets` — lista de rutas predeterminadas
- `GET /routes/presets/{id}` — detalle con lugares en orden

**Eventos `/events`**
- `GET /events` — todos los eventos, ordenados por fecha
- `GET /events/{id}` — detalle
- `POST /events` — crear evento `{ name, description, photo, date, start_time, end_time, address, lat, lng }`
- `DELETE /events/{id}` — eliminar

### Notas importantes
- Las rutas creadas por el usuario **no se guardan en el backend**, se almacenan en el dispositivo con AsyncStorage.
- En PostGIS, `ST_MakePoint` recibe **longitud primero**: `ST_MakePoint(lng, lat)`.
- Para extraer coordenadas en SQL: `ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng`.

---

## Frontend (por desarrollar)

**Stack:** React Native + Expo

**Dependencias planeadas:**
- `expo-location` — ubicación del usuario
- `react-native-maps` — mapa con lugares y eventos
- `@react-native-async-storage/async-storage` — rutas del usuario
- `@react-navigation/native` + `@react-navigation/bottom-tabs` — navegación

**Conectar al backend:**
- En dispositivo físico/emulador Android, usar IP local de la PC (no `localhost`)
- URL base: `http://<IP_LOCAL>:8000`

**Pantallas previstas:** Mapa principal, lista de lugares, detalle de lugar, lista de eventos, detalle de evento, rutas predeterminadas, rutas del usuario (local).

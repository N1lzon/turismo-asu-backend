# Contexto del Proyecto — Turismo Asunción

## Descripción general

App móvil de turismo para Asunción, Paraguay. El proyecto tiene dos partes:
- **Backend:** `/turismo-asu-backend` — FastAPI + PostgreSQL + PostGIS
- **Frontend:** React Native + Expo (carpeta separada)

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

---

## Base de datos

### Tabla `places`
POIs turísticos con columna `location GEOGRAPHY(POINT, 4326)` (PostGIS, indexada con GIST).

Campos: `id, google_place_id, name, category, address, phone, website, rating, total_ratings, opening_hours (JSONB), location, photos (JSONB), created_at`

Categorías válidas: `restaurant`, `museum`, `park`, `hotel`, `bar`, `attraction`

### Tabla `routes`
Rutas turísticas predeterminadas.

Campos: `id, name, description, is_preset (BOOLEAN), start_time (TIME), created_at`

- `start_time` se deriva del horario de apertura del primer lugar de la ruta.
- Las rutas creadas por el usuario **no se guardan en el backend** — viven en el dispositivo con AsyncStorage.

### Tabla `route_places`
Join table entre rutas y lugares.

Campos: `id, route_id (FK), place_id (FK), order_index`

- `order_index` empieza en 0 e indica el orden de visita.

### Tabla `events`
Eventos turísticos/culturales.

Campos: `id, name, description, photo (TEXT/URL), date (DATE), start_time (TIME), end_time (TIME), address, location (GEOGRAPHY, opcional), created_at`

---

## Endpoints

### `GET /places/nearby`
Lugares cercanos a una coordenada, ordenados por distancia.

**Query params:** `lat` (req), `lng` (req), `radius` (default: 2000 metros), `category` (opcional)

**Respuesta:** Array de lugares con `distance_meters` incluido.
```json
[
  {
    "id": 3,
    "name": "Panteón Nacional de los Héroes",
    "category": "attraction",
    "address": "Chile esq. Palmas, Asunción",
    "phone": null,
    "website": null,
    "rating": 4.7,
    "total_ratings": 9200,
    "opening_hours": { "lunes": "07:00 - 19:00", "martes": "07:00 - 19:00", ... },
    "photos": ["https://..."],
    "lat": -25.2867,
    "lng": -57.6452,
    "distance_meters": 320.5
  }
]
```

### `GET /places/search?q=`
Búsqueda de lugares por nombre (case-insensitive, parcial, mín. 2 chars).

**Respuesta:** Array con `id, name, category, address, rating, photos, lat, lng`.

### `GET /places/{id}`
Detalle completo de un lugar: todos los campos de la tabla.

---

### `GET /routes/presets`
Lista de rutas predeterminadas.

```json
[
  {
    "id": 1,
    "name": "Centro Histórico",
    "description": "Recorrido por los principales monumentos y museos del centro de Asunción",
    "start_time": "07:00:00",
    "total_places": 4
  }
]
```

### `GET /routes/presets/{id}`
Detalle de una ruta con sus lugares en orden.

```json
{
  "id": 1,
  "name": "Centro Histórico",
  "description": "Recorrido por los principales monumentos y museos del centro de Asunción",
  "start_time": "07:00:00",
  "places": [
    {
      "id": 3,
      "name": "Panteón Nacional de los Héroes",
      "category": "attraction",
      "address": "...",
      "rating": 4.7,
      "photos": ["https://..."],
      "opening_hours": { ... },
      "lat": -25.2867,
      "lng": -57.6452,
      "order_index": 0
    }
  ]
}
```

---

### `GET /events`
Todos los eventos, ordenados por `date` y `start_time`. Eventos sin ubicación devuelven `lat: null, lng: null`.

```json
[
  {
    "id": 1,
    "name": "Festival de Música",
    "description": "...",
    "photo": "https://...",
    "date": "2026-05-10",
    "start_time": "19:00:00",
    "end_time": "23:00:00",
    "address": "...",
    "lat": -25.2867,
    "lng": -57.6452
  }
]
```

### `GET /events/{id}`
Detalle de un evento.

### `POST /events`
Crear un evento nuevo.

**Body JSON:**
```json
{
  "name": "string",           // requerido
  "description": "string",    // opcional
  "photo": "string (URL)",    // opcional
  "date": "YYYY-MM-DD",       // requerido
  "start_time": "HH:MM",      // requerido
  "end_time": "HH:MM",        // opcional
  "address": "string",        // opcional
  "lat": -25.2867,            // opcional
  "lng": -57.6452             // opcional
}
```

**Respuesta (201):** `{ "id": 1 }`

### `DELETE /events/{id}`
Eliminar un evento. Responde `204 No Content`.

---

## Rutas predeterminadas (seed data)

| ID | Nombre | Start time | Lugares en orden |
|----|--------|-----------|-----------------|
| 1 | Centro Histórico | 07:00 | Panteón Nacional → Casa de la Independencia → Museo del Barro → Mercado 4 |
| 2 | Naturaleza y Relax | 07:00 | Jardín Botánico → Parque Carlos Antonio López → Tierra Colorada |
| 3 | Gastronomía Asuncena | 11:30 | La Preferida → Tierra Colorada → Bar San Roque |

---

## Formato de `opening_hours`

JSONB con días en español. Valores posibles: `"HH:MM - HH:MM"`, `"Cerrado"`, `"24 horas"`.

```json
{
  "lunes": "09:00 - 17:00",
  "martes": "09:00 - 17:00",
  "miércoles": "09:00 - 17:00",
  "jueves": "09:00 - 17:00",
  "viernes": "09:00 - 17:00",
  "sábado": "09:00 - 12:00",
  "domingo": "Cerrado"
}
```

---

## Notas importantes

- En PostGIS, `ST_MakePoint` recibe **longitud primero**: `ST_MakePoint(lng, lat)`.
- Para extraer coordenadas en SQL: `ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng`.
- `start_time` y `end_time` se devuelven como string `"HH:MM:SS"` (formato PostgreSQL TIME).
- `date` en eventos se devuelve como string `"YYYY-MM-DD"`.
- No hay autenticación implementada.
- No hay paginación — todos los endpoints devuelven la colección completa.

---

## Frontend

**Stack:** React Native + Expo

**Dependencias planeadas:**
- `expo-location` — ubicación del usuario
- `react-native-maps` — mapa con lugares y eventos
- `@react-native-async-storage/async-storage` — rutas del usuario (locales)
- `@react-navigation/native` + `@react-navigation/bottom-tabs` — navegación

**Conectar al backend:**
- En dispositivo físico/emulador Android usar la IP local de la PC, no `localhost`
- URL base: `http://<IP_LOCAL>:8000`

**Pantallas previstas:** Mapa principal, lista de lugares, detalle de lugar, lista de eventos, detalle de evento, rutas predeterminadas, rutas del usuario (local).

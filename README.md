# Turismo Asunción — Backend

API REST para la app móvil de turismo de Asunción, Paraguay. Desarrollada con **FastAPI + PostgreSQL + PostGIS**.

---

## Tecnologías

| Componente | Tecnología | Versión |
|---|---|---|
| Lenguaje | Python | 3.11+ |
| Framework web | FastAPI | 0.135.1 |
| Servidor ASGI | Uvicorn | 0.41.0 |
| Base de datos | PostgreSQL + PostGIS | — |
| Adaptador BD | psycopg2-binary | 2.9.11 |
| Variables de entorno | python-dotenv | 1.2.2 |

No se utiliza ORM. Todas las consultas son SQL puro con psycopg2.

---

## Instalación y ejecución

### Requisitos previos

- Python 3.11+
- PostgreSQL con la extensión PostGIS habilitada
- Base de datos `turismo_asu` creada

### Pasos

```bash
# 1. Clonar el repositorio
git clone <url-del-repositorio>
cd turismo-asu-backend

# 2. Crear entorno virtual e instalar dependencias
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con los datos de conexión

# 4. Crear las tablas
psql -d turismo_asu -f scripts/create_tables.sql

# 5. Insertar datos de prueba
python scripts/seed_data.py

# 6. Iniciar el servidor
uvicorn app.main:app --reload
```

El servidor queda disponible en `http://localhost:8000`.
Documentación interactiva (Swagger UI): `http://localhost:8000/docs`.

Para acceder desde un dispositivo móvil en la misma red:

```bash
uvicorn app.main:app --host 0.0.0.0 --reload
```

### Variables de entorno (`.env`)

```
DATABASE_URL=postgresql://USUARIO:CONTRASEÑA@HOST:PUERTO/turismo_asu
GOOGLE_PLACES_API_KEY=       # Reservado, no utilizado actualmente
```

---

## Estructura del proyecto

```
turismo-asu-backend/
├── app/
│   ├── main.py                     # Configuración principal, CORS, registro de routers
│   ├── database/
│   │   └── connection.py           # Función get_connection() con RealDictCursor
│   ├── models/                     # Reservado para modelos Pydantic
│   └── routers/
│       ├── places.py               # Endpoints de lugares turísticos
│       ├── routes.py               # Endpoints de rutas predefinidas
│       └── events.py               # Endpoints de eventos culturales
├── scripts/
│   ├── create_tables.sql           # DDL: creación de tablas e índices
│   ├── migrate_add_start_time.sql  # Migración: columna start_time en routes
│   └── seed_data.py                # Datos de prueba: 10 lugares, 3 rutas
├── .env                            # Variables de entorno (no versionado)
├── requirements.txt
└── README.md
```

---

## Base de datos

El sistema tiene cuatro tablas. Las columnas `location` en `places` y `events` son de tipo `GEOGRAPHY(POINT, 4326)`, gestionadas por PostGIS.

### `places` — Puntos de interés

| Campo | Tipo | Descripción |
|---|---|---|
| id | SERIAL PK | Identificador interno |
| google_place_id | TEXT | ID de Google Places (único, opcional) |
| name | TEXT | Nombre del lugar |
| category | TEXT | Categoría (ver valores abajo) |
| address | TEXT | Dirección |
| phone | TEXT | Teléfono |
| website | TEXT | Sitio web |
| rating | DECIMAL(2,1) | Promedio de estrellas (0.0–5.0) |
| total_ratings | INTEGER | Cantidad de reseñas |
| opening_hours | JSONB | Horarios por día de la semana |
| location | GEOGRAPHY | Coordenadas (PostGIS, indexada con GIST) |
| photos | JSONB | Array de URLs de fotos |
| created_at | TIMESTAMP | Fecha de inserción |

**Categorías válidas:** `restaurant`, `museum`, `park`, `hotel`, `bar`, `attraction`

**Formato de `opening_hours`:**
```json
{
  "lunes": "09:00 - 17:00",
  "sábado": "09:00 - 12:00",
  "domingo": "Cerrado"
}
```

### `routes` — Rutas predefinidas

| Campo | Tipo | Descripción |
|---|---|---|
| id | SERIAL PK | Identificador interno |
| name | TEXT | Nombre de la ruta |
| description | TEXT | Descripción breve |
| is_preset | BOOLEAN | `true` para rutas predefinidas de la app |
| start_time | TIME | Hora de inicio recomendada |
| created_at | TIMESTAMP | Fecha de creación |

> Las rutas creadas por el usuario **no se almacenan en el backend** — viven en el dispositivo vía AsyncStorage.

### `route_places` — Tabla de unión

| Campo | Tipo | Descripción |
|---|---|---|
| id | SERIAL PK | Identificador interno |
| route_id | INTEGER FK | Referencia a `routes.id` (cascade delete) |
| place_id | INTEGER FK | Referencia a `places.id` (cascade delete) |
| order_index | INTEGER | Orden de visita dentro de la ruta (base 0) |

### `events` — Eventos culturales

| Campo | Tipo | Descripción |
|---|---|---|
| id | SERIAL PK | Identificador interno |
| name | TEXT | Nombre del evento |
| description | TEXT | Descripción (opcional) |
| photo | TEXT | URL de foto (opcional) |
| date | DATE | Fecha del evento |
| start_time | TIME | Hora de inicio |
| end_time | TIME | Hora de fin (opcional) |
| address | TEXT | Dirección (opcional) |
| location | GEOGRAPHY | Coordenadas (opcional, indexada con GIST) |
| created_at | TIMESTAMP | Fecha de inserción |

---

## Endpoints

### Lugares — `/places`

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/places/nearby` | Lugares cercanos a una coordenada, ordenados por distancia |
| GET | `/places/search` | Búsqueda por nombre (parcial, insensible a mayúsculas) |
| GET | `/places/{id}` | Detalle completo de un lugar |

#### GET /places/nearby

| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| lat | float | ✓ | — | Latitud del usuario |
| lng | float | ✓ | — | Longitud del usuario |
| radius | int | | 2000 | Radio de búsqueda en metros |
| category | string | | — | Filtrar por categoría |

```bash
curl "http://localhost:8000/places/nearby?lat=-25.2867&lng=-57.6470&radius=3000"
curl "http://localhost:8000/places/nearby?lat=-25.2867&lng=-57.6470&category=museum"
```

#### GET /places/search

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| q | string | ✓ | Texto a buscar (mínimo 2 caracteres) |

```bash
curl "http://localhost:8000/places/search?q=museo"
```

#### GET /places/{id}

```bash
curl "http://localhost:8000/places/3"
```

---

### Rutas — `/routes`

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/routes/presets` | Lista de rutas predefinidas con total de lugares |
| GET | `/routes/presets/{id}` | Detalle de una ruta con sus lugares en orden de visita |

```bash
curl "http://localhost:8000/routes/presets"
curl "http://localhost:8000/routes/presets/1"
```

---

### Eventos — `/events`

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/events` | Lista todos los eventos ordenados por fecha |
| GET | `/events/{id}` | Detalle de un evento |
| POST | `/events` | Crea un nuevo evento |
| DELETE | `/events/{id}` | Elimina un evento |

#### POST /events

Campos requeridos: `name`, `date`, `start_time`. El resto son opcionales.

```json
{
  "name": "Festival de Arte",
  "description": "Festival de arte contemporáneo",
  "date": "2026-06-15",
  "start_time": "18:00",
  "end_time": "22:00",
  "address": "Parque Carlos Antonio López",
  "lat": -25.2820,
  "lng": -57.6480
}
```

Respuesta `201 Created`: `{ "id": 42 }`

---

## Notas

- Las consultas geoespaciales usan `ST_DWithin()` y `ST_Distance()` de PostGIS. La columna `location` se almacena como `GEOGRAPHY(POINT, 4326)` (WGS84).
- En `ST_MakePoint(lng, lat)` la **longitud va primero**.
- Cada endpoint abre y cierra su propia conexión a la base de datos (sin connection pooling).
- El servidor expone documentación interactiva en `/docs` y `/redoc`.

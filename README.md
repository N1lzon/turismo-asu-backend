# Turismo Asunción — Backend

API REST para la app móvil de turismo de Asunción, Paraguay, con un panel de administración asociado. Desarrollada con **FastAPI + PostgreSQL + PostGIS**.

---

## Tecnologías

| Componente | Tecnología | Versión |
|---|---|---|
| Lenguaje | Python | 3.11+ |
| Framework web | FastAPI | 0.115.12 |
| Servidor ASGI | Uvicorn | 0.34.3 |
| Base de datos | PostgreSQL + PostGIS | — |
| Adaptador BD | psycopg2-binary | 2.9.10 |
| Autenticación admin | python-jose (JWT) | 3.3.0 |
| Subida de archivos | python-multipart | 0.0.20 |
| Cliente HTTP | requests | 2.32.3 |
| Variables de entorno | python-dotenv | 1.1.0 |

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
cp .env.example .env          # o crear .env manualmente, ver tabla abajo
# Editar .env con los datos de conexión y credenciales de admin

# 4. Crear las tablas
psql -d turismo_asu -f scripts/create_tables.sql

# 5. Insertar datos de prueba
python scripts/seed_data.py

# 6. Iniciar el servidor
uvicorn app.main:app --reload
```

El servidor queda disponible en `http://localhost:8000`.
Documentación interactiva (Swagger UI en `/docs`, ReDoc en `/redoc`) solo se expone cuando `ENV=development`.

Para acceder desde un dispositivo móvil en la misma red:

```bash
uvicorn app.main:app --host 0.0.0.0 --reload
```

### Alternativa con Docker

```bash
cd docker-setup
cp .env.example .env          # definir DB_PASSWORD
# completar también API_KEY, ADMIN_USERNAME, ADMIN_PASSWORD, JWT_SECRET, API_BASE_URL en .env
docker compose up -d
```

Levanta un contenedor de PostgreSQL+PostGIS (con `create_tables.sql` aplicado automáticamente) y la API en el puerto `8000`. Las fotos subidas se persisten en el volumen `photos_data`.

### Variables de entorno (`.env`)

| Variable | Descripción |
|---|---|
| `DATABASE_URL` | Cadena de conexión PostgreSQL, ej. `postgresql://USUARIO:CONTRASEÑA@HOST:PUERTO/turismo_asu` |
| `ENV` | `development` habilita `/docs`, `/redoc` y `/openapi.json`; cualquier otro valor los deshabilita |
| `API_KEY` | Clave estática (header `X-API-Key`) para crear/eliminar eventos |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Credenciales del usuario administrador (login del panel) |
| `JWT_SECRET` | Secreto usado para firmar/verificar los tokens JWT del panel de admin |
| `ADMIN_ORIGIN` | Origen adicional permitido por CORS para el panel de administración (opcional) |
| `API_BASE_URL` | URL pública base usada para construir las URLs de las fotos subidas (ej. `http://localhost:8000`) |
| `GOOGLE_PLACES_API_KEY` | Reservado, no utilizado actualmente |

---

## Estructura del proyecto

```
turismo-asu-backend/
├── app/
│   ├── main.py                       # Configuración principal, CORS, static files, registro de routers
│   ├── dependencies.py               # Dependencias de auth: API key (X-API-Key) y JWT (panel admin)
│   ├── database/
│   │   └── connection.py             # Función get_connection() con RealDictCursor
│   └── routers/
│       ├── places.py                 # Endpoints públicos de lugares turísticos
│       ├── routes.py                 # Endpoints públicos de rutas predefinidas
│       ├── events.py                 # Endpoints de eventos culturales (lectura pública, escritura con API key)
│       └── admin.py                  # Panel de administración: login JWT, CRUD de lugares/rutas, fotos, métricas
├── scripts/
│   ├── create_tables.sql             # DDL: creación de tablas e índices
│   ├── migrate_add_start_time.sql    # Migración: columna start_time en routes
│   ├── migrate_add_metrics.sql       # Migración: tabla metrics
│   ├── seed_data.py                  # Datos de prueba: 10 lugares, 3 rutas
│   ├── populate_from_osm.py          # Pobla lugares reales de Asunción vía Overpass API (OpenStreetMap)
│   ├── seed_route_places.py          # Asocia lugares importados de OSM a las 3 rutas predefinidas
│   └── seed_route_places.sql         # Equivalente en SQL puro
├── static/photos/                    # Fotos subidas vía el panel de admin (servidas en /static)
├── docker-setup/
│   ├── Dockerfile                    # Imagen de la API
│   ├── docker-compose.yml            # Servicios db (Postgres+PostGIS) y api
│   └── .env.example                  # Variables requeridas por docker-compose
├── places_dummy.json                 # Datos de referencia de lugares (desarrollo)
├── .env                              # Variables de entorno (no versionado)
├── requirements.txt
└── README.md
```

---

## Base de datos

El sistema tiene cinco tablas. Las columnas `location` en `places` y `events` son de tipo `GEOGRAPHY(POINT, 4326)`, gestionadas por PostGIS.

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
| photos | JSONB | Array de URLs de fotos (default `[]`) |
| created_at | TIMESTAMP | Fecha de inserción |

**Categorías válidas:** `gastronomia`, `hoteles`, `lugares`

- **gastronomia** — restaurantes, cafés, bares, panaderías, comida rápida, discotecas
- **hoteles** — hoteles, moteles, hoteles resort
- **lugares** — atracciones, museos, galerías de arte, parques, monumentos, iglesias, zoológicos, centros culturales

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

> Las rutas creadas por el usuario final **no se almacenan en el backend** — viven en el dispositivo vía AsyncStorage. Las rutas administradas desde el panel sí se persisten aquí.

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

### `metrics` — Métricas del dashboard de admin

| Campo | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | Fila única (`id = 1`) |
| data | JSONB | Métricas arbitrarias administradas desde el panel, combinadas en `GET /admin/metrics` con datos calculados de `places` |

---

## Autenticación

Hay dos esquemas de autenticación independientes (`app/dependencies.py`):

| Esquema | Header | Uso |
|---|---|---|
| API Key | `X-API-Key: <API_KEY>` | Crear/eliminar eventos (`POST`/`DELETE /events`) |
| JWT (Bearer) | `Authorization: Bearer <token>` | Todos los endpoints bajo `/admin` (excepto el login) |

El token JWT se obtiene en `POST /admin/auth/login` y expira a las 8 horas.

---

## Endpoints

### Lugares — `/places` (públicos, sin autenticación)

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
curl "http://localhost:8000/places/nearby?lat=-25.2867&lng=-57.6470&category=lugares"
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

### Rutas — `/routes` (públicos, sin autenticación)

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

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/events` | — | Lista todos los eventos ordenados por fecha |
| GET | `/events/{id}` | — | Detalle de un evento |
| POST | `/events` | API key | Crea un nuevo evento |
| DELETE | `/events/{id}` | API key | Elimina un evento |

#### POST /events

Campos requeridos: `name`, `date`, `start_time`. El resto son opcionales.

```bash
curl -X POST "http://localhost:8000/events" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Festival de Arte",
    "description": "Festival de arte contemporáneo",
    "date": "2026-06-15",
    "start_time": "18:00",
    "end_time": "22:00",
    "address": "Parque Carlos Antonio López",
    "lat": -25.2820,
    "lng": -57.6480
  }'
```

Respuesta `201 Created`: `{ "id": 42 }`

---

### Administración — `/admin` (requiere JWT salvo el login)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/admin/auth/login` | Login con usuario/contraseña, devuelve un access token JWT |
| GET | `/admin/places` | Lista todos los lugares |
| GET | `/admin/places/{id}` | Detalle de un lugar |
| PUT | `/admin/places/{id}` | Actualiza campos de un lugar (parcial) |
| DELETE | `/admin/places/{id}` | Elimina un lugar (y sus fotos en disco) |
| POST | `/admin/places/{id}/photos` | Sube una foto (jpg, jpeg, png, webp) para un lugar |
| DELETE | `/admin/places/{id}/photos` | Elimina una foto de un lugar (por URL) |
| POST | `/admin/routes` | Crea una ruta, opcionalmente con sus lugares en orden |
| GET | `/admin/routes` | Lista todas las rutas con sus lugares |
| GET | `/admin/routes/{id}` | Detalle de una ruta con sus lugares |
| PUT | `/admin/routes/{id}` | Actualiza nombre/descripción/lugares de una ruta |
| DELETE | `/admin/routes/{id}` | Elimina una ruta |
| GET | `/admin/metrics` | Métricas almacenadas + estadísticas calculadas de `places` |
| PUT | `/admin/metrics` | Reemplaza el JSON de métricas almacenadas |

#### POST /admin/auth/login

Recibe `application/x-www-form-urlencoded` (`OAuth2PasswordRequestForm`): campos `username` y `password`.

```bash
curl -X POST "http://localhost:8000/admin/auth/login" \
  -d "username=$ADMIN_USERNAME&password=$ADMIN_PASSWORD"
```

Respuesta: `{ "access_token": "<jwt>", "token_type": "bearer" }`. Usar ese token en `Authorization: Bearer <jwt>` para el resto de `/admin`.

#### PUT /admin/places/{id}

Body parcial; solo se actualizan los campos enviados. Acepta `name`, `category` (debe ser una de `gastronomia`, `hoteles`, `lugares`), `address`, `phone`, `website`, `rating`, `total_ratings`, `opening_hours`, y `lat`/`lng` (ambos juntos para actualizar `location`).

#### POST /admin/places/{id}/photos

`multipart/form-data` con campo `file`. Guarda el archivo en `static/photos/` y agrega la URL pública (`API_BASE_URL` + ruta) al array `photos` del lugar.

#### GET /admin/metrics

Combina el JSON libre guardado en la tabla `metrics` con estadísticas calculadas en el momento: total de lugares, conteo por categoría, lugares sin fotos y total de fotos.

---

## Notas

- Las consultas geoespaciales usan `ST_DWithin()` y `ST_Distance()` de PostGIS. La columna `location` se almacena como `GEOGRAPHY(POINT, 4326)` (WGS84).
- En `ST_MakePoint(lng, lat)` la **longitud va primero**.
- Cada endpoint abre y cierra su propia conexión a la base de datos (sin connection pooling).
- El servidor expone documentación interactiva en `/docs` y `/redoc` únicamente cuando `ENV=development`.
- Los archivos estáticos (fotos subidas) se sirven desde `/static`, mapeado al directorio `static/` del proyecto.

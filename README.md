# Turismo Asunción — Backend

API REST para la app móvil de turismo de Asunción, Paraguay. Desarrollada con FastAPI y PostgreSQL + PostGIS.

---

## Tecnologías

- **FastAPI** — framework web para Python
- **PostgreSQL** — base de datos relacional
- **PostGIS** — extensión de PostgreSQL para consultas geoespaciales
- **psycopg2** — conector de Python para PostgreSQL

---

## Estructura del proyecto
```
turismo-asu-backend/
├── app/
│   ├── main.py                  # Configuración principal de FastAPI
│   ├── routers/
│   │   ├── places.py            # Endpoints de lugares
│   │   └── routes.py            # Endpoints de rutas predeterminadas
│   └── database/
│       └── connection.py        # Conexión a PostgreSQL
├── scripts/
│   ├── create_tables.sql        # Crea las tablas en la base de datos
│   ├── seed_data.py             # Inserta datos de prueba
│   └── populate_from_google.py  # (Pendiente) Carga datos reales desde Google Places API
├── .env                         # Variables de entorno — NO subir al repositorio
├── .gitignore
└── README.md
```

---

## Base de datos

El proyecto usa tres tablas:

### `places` — Puntos de interés

Almacena todos los lugares turísticos de Asunción.

| Campo | Tipo | Descripción |
|---|---|---|
| id | SERIAL | ID interno |
| google_place_id | TEXT | ID de Google Places (para datos reales) |
| name | TEXT | Nombre del lugar |
| category | TEXT | Categoría del lugar (ver valores más abajo) |
| address | TEXT | Dirección |
| phone | TEXT | Teléfono de contacto |
| website | TEXT | Sitio web |
| rating | DECIMAL | Promedio de estrellas (0.0 - 5.0) |
| total_ratings | INTEGER | Cantidad de reseñas |
| opening_hours | JSONB | Horarios por día de la semana |
| location | GEOGRAPHY | Coordenadas geográficas (PostGIS) |
| photos | JSONB | Lista de URLs de fotos |
| created_at | TIMESTAMP | Fecha de inserción |

**Categorías disponibles:** `restaurant`, `museum`, `park`, `hotel`, `bar`, `attraction`

**Ejemplo de `opening_hours`:**
```json
{
  "lunes": "09:00 - 17:00",
  "martes": "09:00 - 17:00",
  "sábado": "09:00 - 12:00",
  "domingo": "Cerrado"
}
```

---

### `routes` — Rutas predeterminadas

Almacena las rutas turísticas recomendadas que se muestran en la app.

| Campo | Tipo | Descripción |
|---|---|---|
| id | SERIAL | ID interno |
| name | TEXT | Nombre de la ruta |
| description | TEXT | Descripción breve |
| is_preset | BOOLEAN | Siempre `true` para rutas predeterminadas |
| created_at | TIMESTAMP | Fecha de creación |

---

### `route_places` — Lugares de cada ruta

Relaciona rutas con lugares y define el orden de visita.

| Campo | Tipo | Descripción |
|---|---|---|
| id | SERIAL | ID interno |
| route_id | INTEGER | Referencia a `routes.id` |
| place_id | INTEGER | Referencia a `places.id` |
| order_index | INTEGER | Orden del lugar dentro de la ruta (0, 1, 2...) |

---

## Endpoints

### Lugares — `/places`

#### `GET /places/nearby` — Lugares cercanos

Devuelve los lugares más cercanos a la ubicación del usuario, ordenados por distancia.

| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| lat | float | ✓ | — | Latitud del usuario |
| lng | float | ✓ | — | Longitud del usuario |
| radius | int | | 2000 | Radio de búsqueda en metros |
| category | string | | — | Filtrar por categoría |

**Ejemplo:**
```bash
curl "http://localhost:8000/places/nearby?lat=-25.2867&lng=-57.6470&radius=3000"
curl "http://localhost:8000/places/nearby?lat=-25.2867&lng=-57.6470&category=restaurant"
```

---

#### `GET /places/search` — Buscar por nombre

Busca lugares cuyo nombre contenga el texto ingresado.

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| q | string | ✓ | Texto a buscar (mínimo 2 caracteres) |

**Ejemplo:**
```bash
curl "http://localhost:8000/places/search?q=museo"
```

---

#### `GET /places/{id}` — Detalle de un lugar

Devuelve toda la información de un lugar específico.

**Ejemplo:**
```bash
curl "http://localhost:8000/places/1"
```

---

### Rutas — `/routes`

#### `GET /routes/presets` — Lista de rutas predeterminadas

Devuelve todas las rutas recomendadas con el total de lugares de cada una.

**Ejemplo:**
```bash
curl "http://localhost:8000/routes/presets"
```

---

#### `GET /routes/presets/{id}` — Detalle de una ruta predeterminada

Devuelve la información completa de una ruta con todos sus lugares en orden de visita.

**Ejemplo:**
```bash
curl "http://localhost:8000/routes/presets/1"
```

---

## Notas

- Las rutas creadas por el usuario **no se guardan en el backend** — se almacenan localmente en el dispositivo con AsyncStorage.
- El campo `location` usa el tipo `GEOGRAPHY` de PostGIS, lo que permite calcular distancias reales en metros directamente en las consultas SQL.
- El servidor expone documentación interactiva en `http://localhost:8000/docs`.
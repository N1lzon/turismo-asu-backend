# SETUP — turismo-asu-backend

Este archivo está escrito para ser leído por Claude Code y ejecutado automáticamente.
Cuando el usuario diga "configura el proyecto" o similar, leer este archivo y ejecutar cada paso en orden.

## Prerequisitos — verificar antes de empezar

```bash
python3 --version   # necesita 3.9+
psql --version      # necesita PostgreSQL con PostGIS disponible
pip --version
```

Reportar qué falta antes de continuar.

## Paso 1 — Clonar el repo (si no existe el directorio)

```bash
git clone <repo-url> turismo-asu-backend
cd turismo-asu-backend
```

Si el directorio ya existe, omitir este paso.

## Paso 2 — Crear y activar entorno virtual

```bash
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows
```

## Paso 3 — Instalar dependencias Python

No hay requirements.txt. Instalar estas versiones exactas:

```bash
pip install \
  fastapi==0.135.1 \
  psycopg2-binary==2.9.11 \
  uvicorn==0.41.0 \
  python-dotenv==1.2.2
```

## Paso 4 — Crear el archivo .env

El archivo está en .gitignore y debe crearse manualmente. Crear `.env` en la raíz del proyecto:

```
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/turismo_asu
GOOGLE_PLACES_API_KEY=
```

Valor típico para desarrollo local:
`DATABASE_URL=postgresql://postgres:password@localhost:5432/turismo_asu`

Pedir al usuario el valor correcto si no se conoce.

## Paso 5 — Crear la base de datos PostgreSQL

```bash
createdb turismo_asu
# o si se necesita especificar usuario:
psql -U postgres -c "CREATE DATABASE turismo_asu;"
```

## Paso 6 — Habilitar PostGIS y crear las tablas

```bash
psql -d turismo_asu -c "CREATE EXTENSION IF NOT EXISTS postgis;"
psql -d turismo_asu -f scripts/create_tables.sql
```

Esto crea:
- `places` — POIs turísticos con columna `location GEOGRAPHY(POINT, 4326)` (índice GIST)
- `routes` — rutas turísticas predeterminadas
- `route_places` — tabla de unión rutas↔lugares
- `events` — eventos con fecha y ubicación opcional

## Paso 7 — Poblar la base de datos con datos de prueba

```bash
python scripts/seed_data.py
```

Inserta 10 lugares en Asunción y 3 rutas predeterminadas. Borra los datos existentes primero.

## Paso 8 — Levantar el servidor

```bash
uvicorn app.main:app --reload
```

Servidor en http://localhost:8000  
Docs interactivos en http://localhost:8000/docs

## Paso 9 — Verificar que funciona

```bash
curl http://localhost:8000/
# Esperado: {"message":"Turismo Asunción API funcionando"}

curl http://localhost:8000/places
# Esperado: array JSON con los lugares
```

---

## Estructura del proyecto

```
app/
  main.py                  — app FastAPI, CORS, registro de routers
  database/connection.py   — get_connection() con psycopg2 + RealDictCursor
  routers/
    places.py              — endpoints /places (consultas geoespaciales PostGIS)
    routes.py              — endpoints /routes (rutas turísticas)
    events.py              — endpoints /events
scripts/
  create_tables.sql        — DDL de todas las tablas
  seed_data.py             — inserta lugares y rutas de prueba
```

## Errores comunes

| Error | Causa | Solución |
|-------|-------|----------|
| `could not load library "postgis-3.so"` | PostGIS no instalado | Ubuntu: `sudo apt install postgresql-XX-postgis-3` / macOS: `brew install postgis` |
| `connection refused` | PostgreSQL no está corriendo | `sudo systemctl start postgresql` o `brew services start postgresql` |
| `role "postgres" does not exist` | Usuario PostgreSQL diferente | Ajustar `DATABASE_URL` con el usuario correcto |
| `ModuleNotFoundError: No module named 'app'` | Uvicorn corrido desde carpeta incorrecta | Correr desde la raíz del proyecto, no desde dentro de `app/` |
| `DELETE FROM events` falta en seed | La tabla events existe pero seed no la limpia | Normal, seed solo limpia places/routes/route_places |

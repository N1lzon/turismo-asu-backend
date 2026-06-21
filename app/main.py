import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routers import places, routes, events, admin

_is_dev = os.getenv("ENV", "production") == "development"

app = FastAPI(
    title="Turismo Asunción API",
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)

_admin_origin = os.getenv("ADMIN_ORIGIN", "")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",
        "http://localhost:19006",
        *([_admin_origin] if _admin_origin else []),
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(places.router)
app.include_router(routes.router)
app.include_router(events.router)
app.include_router(admin.router)

@app.get("/")
def root():
    return {"message": "Turismo Asunción API funcionando"}
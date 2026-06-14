import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import places, routes, events

_is_dev = os.getenv("ENV", "production") == "development"

app = FastAPI(
    title="Turismo Asunción API",
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",   # Expo web dev
        "http://localhost:19006",  # Expo web alternativo
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(places.router)
app.include_router(routes.router)
app.include_router(events.router)

@app.get("/")
def root():
    return {"message": "Turismo Asunción API funcionando"}
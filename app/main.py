from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import places, routes

app = FastAPI(title="Turismo Asunción API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(places.router)
app.include_router(routes.router)

@app.get("/")
def root():
    return {"message": "Turismo Asunción API funcionando"}
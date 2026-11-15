from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import connections, discovery, health, migration_plans, projects, users
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.4.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(connections.router, prefix="/api/v1")
app.include_router(discovery.router, prefix="/api/v1")
app.include_router(migration_plans.router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "application": "Conduit",
        "version": "0.4.0",
        "docs": "/docs",
    }

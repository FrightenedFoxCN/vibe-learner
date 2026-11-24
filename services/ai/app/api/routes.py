from fastapi import APIRouter

from app.api.routers import (
    documents,
    persona_scene,
    planning,
    study,
    study_notes,
    system,
)

router = APIRouter()
for _child in (
    documents.router,
    planning.router,
    study.router,
    study_notes.router,
    persona_scene.router,
    system.router,
):
    router.include_router(_child)

from fastapi import APIRouter

from app.api.routers import documents, persona_scene, planning, study, system

router = APIRouter()
for _child in (
    documents.router,
    planning.router,
    study.router,
    persona_scene.router,
    system.router,
):
    router.include_router(_child)

# Placeholder workflow routes
from fastapi import APIRouter

router = APIRouter()

@router.post("/")
async def create_workflow():
    return {"message": "Workflow endpoint"}

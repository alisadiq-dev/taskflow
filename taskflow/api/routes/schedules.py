# Placeholder schedule routes
from fastapi import APIRouter

router = APIRouter()

@router.post("/")
async def create_schedule():
    return {"message": "Schedule endpoint"}

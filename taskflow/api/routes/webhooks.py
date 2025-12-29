# Placeholder webhook routes
from fastapi import APIRouter

router = APIRouter()

@router.post("/")
async def create_webhook():
    return {"message": "Webhook endpoint"}

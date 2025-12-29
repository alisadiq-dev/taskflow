# Placeholder monitoring routes
from fastapi import APIRouter

router = APIRouter()

@router.get("/metrics")
async def get_metrics():
    return {"metrics": "placeholder"}

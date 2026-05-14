from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.core.schemas import TTSRequest, TTSResponse
from app.services.tts_service import synthesize_tts


router = APIRouter(prefix="/tts", tags=["tts"], dependencies=[Depends(require_auth)])


@router.post("/generate", response_model=TTSResponse)
async def generate_tts(payload: TTSRequest) -> TTSResponse:
    return await synthesize_tts(payload)
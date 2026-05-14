from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.core.schemas import AgentConfig, AgentConfigUpdate
from app.services.store import store


router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(require_auth)])


@router.get("/config", response_model=AgentConfig)
async def get_config() -> AgentConfig:
    return store.get_agent_config()


@router.put("/config", response_model=AgentConfig)
async def update_config(payload: AgentConfigUpdate) -> AgentConfig:
    return store.update_agent_config(payload.model_dump())
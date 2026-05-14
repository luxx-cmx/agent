from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes_agent import router as agent_router
from app.api.routes_conversations import router as conversations_router
from app.api.routes_tools import router as tools_router
from app.api.routes_tts import router as tts_router
from app.core.config import AUDIO_DIR, settings
from app.services.model_provider import get_llm_runtime_source
from app.services.store import store
from app.services.tts_service import get_tts_runtime_source


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.initialize()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static/audio", StaticFiles(directory=AUDIO_DIR), name="audio")


@app.get("/health")
async def healthcheck():
    return {
        "status": "ok",
        "store": store.backend_name,
        "llm_provider": get_llm_runtime_source(),
        "tts_provider": get_tts_runtime_source(),
    }


app.include_router(conversations_router, prefix=settings.api_prefix)
app.include_router(tools_router, prefix=settings.api_prefix)
app.include_router(agent_router, prefix=settings.api_prefix)
app.include_router(tts_router, prefix=settings.api_prefix)
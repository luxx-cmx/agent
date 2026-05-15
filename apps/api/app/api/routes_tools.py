from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.services.tool_registry import TOOLS
from app.core.schemas import (
    DatabaseQueryRequest,
    DatabaseQueryResponse,
    DatabaseSchemaResponse,
    ImageGenerationRequest,
    ImageGenerationResponse,
)
from app.services.tools import database_query_tool, generate_image, get_database_schema_summary


router = APIRouter(prefix="/tools", tags=["tools"], dependencies=[Depends(require_auth)])


@router.get("")
async def list_tools():
    return {
        "items": [tool.model_dump() for tool in TOOLS],
        "count": len(TOOLS),
    }


@router.get("/database/schema", response_model=DatabaseSchemaResponse)
async def get_database_schema() -> DatabaseSchemaResponse:
    return DatabaseSchemaResponse(**get_database_schema_summary())


@router.post("/database/query", response_model=DatabaseQueryResponse)
async def execute_database_query(payload: DatabaseQueryRequest) -> DatabaseQueryResponse:
    result = await database_query_tool(payload.sql)
    return DatabaseQueryResponse(**result)


@router.post("/image/generate", response_model=ImageGenerationResponse)
async def generate_image_route(payload: ImageGenerationRequest) -> ImageGenerationResponse:
    result = await generate_image(payload.prompt, payload.style, payload.size)
    return ImageGenerationResponse(**result)
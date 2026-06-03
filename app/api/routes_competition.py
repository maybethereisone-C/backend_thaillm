import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import OutputGuard, PromptInjectionGuard
from app.core.settings import Settings, get_settings
from app.schemas.competition import AgentRequest, AgentResponse
from app.services.agent_service import AgentConfig, run_agent as _run_agent
from app.services.audit_service import write_audit_trail

# No /v1 prefix, no auth — the scoring server calls this endpoint directly.
router = APIRouter(tags=["competition"])


@router.post(
    "/agent/thaillm",
    response_model=AgentResponse,
    responses={
        422: {"description": "Request validation failed"},
        503: {"description": "ThaiLLM endpoint not configured"},
        500: {"description": "Agent pipeline error"},
    },
)
async def agent_thaillm(
    req: AgentRequest,
    settings: Settings = Depends(get_settings),
) -> AgentResponse:
    if not settings.thaillm_base_url:
        raise HTTPException(status_code=503, detail="ThaiLLM endpoint not configured")
    if settings.prompt_guard_enabled:
        PromptInjectionGuard().enforce_text(req.question)
    id_ = str(uuid.uuid4())
    config = AgentConfig(
        model_id=settings.thaillm_model_id,
        base_url=str(settings.thaillm_base_url),
        api_key=(
            settings.thaillm_api_key.get_secret_value()
            if settings.thaillm_api_key
            else None
        ),
        agent_db_path=settings.agent_db_path,
        agent_src_path=settings.agent_src_path,
        timeout=settings.request_timeout_seconds,
    )
    answer, tokens, trace = await _run_agent(req.question, config)
    if settings.prompt_guard_enabled:
        OutputGuard().enforce_text(answer)
    await asyncio.to_thread(write_audit_trail, id_, trace, settings.audit_trail_dir)
    return AgentResponse(id=id_, answer=answer, total_output_token_count=tokens)

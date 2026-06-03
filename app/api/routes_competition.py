import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import OutputGuard, PromptInjectionGuard
from app.core.settings import Settings, get_settings
from app.schemas.competition import AgentRequest, AgentResponse
from app.services.agent_service import AgentConfig, run_agent as _run_agent
from app.services.audit_service import write_audit_trail
from app.services.result_logger import log_result

# No /v1 prefix, no auth — the scoring server calls this endpoint directly.
router = APIRouter(tags=["competition"])


@router.post(
    "/agent/thaillm",
    response_model=AgentResponse,
    responses={
        422: {"description": "Request validation failed"},
        503: {"description": "Model endpoint not configured"},
        500: {"description": "Agent pipeline error"},
    },
)
async def agent_thaillm(
    req: AgentRequest,
    settings: Settings = Depends(get_settings),
) -> AgentResponse:
    # Call a local OpenAI-compatible model server (no API key). Config comes from
    # the LLM_THAILLM_* settings; base_url must point at the local llama-server.
    _log = logging.getLogger("llm.thaillm")
    base_url = str(settings.thaillm_base_url) if settings.thaillm_base_url else None
    if not base_url:
        raise HTTPException(status_code=503, detail="Model endpoint not configured")
    _log.info(json.dumps({
        "event": "thaillm_config",
        "stage": "route",
        "base_url": base_url,
        "model_id": settings.thaillm_model_id or None,
        "audit_trail_dir": settings.audit_trail_dir,
        "agent_db_path": settings.agent_db_path,
        "agent_src_path": settings.agent_src_path,
    }))
    if settings.prompt_guard_enabled:
        PromptInjectionGuard().enforce_text(req.question)
    id_ = str(uuid.uuid4())
    config = AgentConfig(
        model_id=settings.thaillm_model_id,
        base_url=base_url,
        api_key=None,
        agent_db_path=settings.agent_db_path,
        agent_src_path=settings.agent_src_path,
        timeout=settings.request_timeout_seconds,
    )
    answer, tokens, trace = await _run_agent(req.question, config)
    if settings.prompt_guard_enabled:
        OutputGuard().enforce_text(answer)
    await asyncio.to_thread(write_audit_trail, id_, trace, settings.audit_trail_dir)
    await asyncio.to_thread(
        log_result, settings.results_log_dir, id_, req.question, answer, tokens, trace
    )
    return AgentResponse(id=id_, answer=answer, total_output_token_count=tokens)

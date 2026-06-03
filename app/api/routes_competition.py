import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends

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
    # Upstream config is hardcoded literally at each call site; env is no longer
    # the source of truth for base_url/model_id/api_key/audit_trail_dir. Log what
    # env resolved alongside the hardcoded values actually used, to pinpoint where
    # a misconfiguration originates.
    _log = logging.getLogger("llm.thaillm")
    _env_key = (
        settings.thaillm_api_key.get_secret_value()
        if settings.thaillm_api_key
        else None
    )
    _log.info(json.dumps({
        "event": "thaillm_config",
        "stage": "route",
        "env_base_url": str(settings.thaillm_base_url) if settings.thaillm_base_url else None,
        "env_model_id": settings.thaillm_model_id or None,
        "env_api_key_prefix": _env_key[:6] if _env_key else None,
        "env_audit_trail_dir": settings.audit_trail_dir,
        "used_base_url": "http://thaillm.or.th/api/v1",
        "used_model_id": "typhoon-s-thaillm-8b-instruct",
        "used_api_key_prefix": "AIR5lI",
        "used_audit_trail_dir": "audit_trails",
        "agent_db_path": settings.agent_db_path,
        "agent_src_path": settings.agent_src_path,
    }))
    if settings.prompt_guard_enabled:
        PromptInjectionGuard().enforce_text(req.question)
    id_ = str(uuid.uuid4())
    config = AgentConfig(
        model_id="typhoon-s-thaillm-8b-instruct",
        base_url="http://thaillm.or.th/api/v1",
        api_key="AIR5lIG7mZfOXbca7haN3wvyAsgVwzpC",
        agent_db_path=settings.agent_db_path,
        agent_src_path=settings.agent_src_path,
        timeout=settings.request_timeout_seconds,
    )
    answer, tokens, trace = await _run_agent(req.question, config)
    if settings.prompt_guard_enabled:
        OutputGuard().enforce_text(answer)
    await asyncio.to_thread(write_audit_trail, id_, trace, settings.audit_trail_dir)
    return AgentResponse(id=id_, answer=answer, total_output_token_count=tokens)

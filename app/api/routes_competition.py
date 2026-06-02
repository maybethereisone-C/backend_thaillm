import uuid

from fastapi import APIRouter, Depends

from app.core.settings import Settings, get_settings
from app.schemas.competition import AgentRequest, AgentResponse
from app.services.agent_service import AgentConfig, run_agent as _run_agent
from app.services.audit_service import write_audit_trail

# No /v1 prefix, no auth — the scoring server calls this endpoint directly.
router = APIRouter(tags=["competition"])


@router.post("/agent/thaillm", response_model=AgentResponse)
async def agent_thaillm(
    req: AgentRequest,
    settings: Settings = Depends(get_settings),
) -> AgentResponse:
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
    )
    answer, tokens, trace = await _run_agent(req.question, config)
    write_audit_trail(id_, trace, settings.audit_trail_dir)
    return AgentResponse(id=id_, answer=answer, total_output_token=tokens)

import pytest
from pydantic import ValidationError

from app.schemas.competition import AgentRequest, AgentResponse


def test_agent_request_rejects_empty_question():
    with pytest.raises(ValidationError):
        AgentRequest(question="")


def test_agent_request_rejects_oversized_question():
    with pytest.raises(ValidationError):
        AgentRequest(question="x" * 4097)


def test_agent_request_accepts_valid_question():
    req = AgentRequest(question="What is the MSRP of NT-LT-001?")
    assert req.question == "What is the MSRP of NT-LT-001?"


def test_agent_request_accepts_max_length_question():
    req = AgentRequest(question="x" * 4096)
    assert len(req.question) == 4096


def test_agent_response_shape():
    resp = AgentResponse(id="uuid-1", answer="45900", total_output_token=42)
    assert resp.total_output_token == 42

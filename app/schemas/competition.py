from pydantic import BaseModel, Field

_MAX_QUESTION_LEN = 4096


class AgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=_MAX_QUESTION_LEN)


class AgentResponse(BaseModel):
    id: str
    answer: str
    total_output_token_count: int

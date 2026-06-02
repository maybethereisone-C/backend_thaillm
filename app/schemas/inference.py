from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class CompletionRequest(BaseModel):
    model: str = "default"
    prompt: str = Field(min_length=1)
    max_tokens: int | None = Field(default=None, gt=0)
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)


class CompletionChoice(BaseModel):
    index: int
    text: str
    finish_reason: str | None = None


class CompletionResponse(BaseModel):
    model: str
    choices: list[CompletionChoice]
    usage: Usage = Field(default_factory=Usage)


class ChatCompletionRequest(BaseModel):
    model: str = "default"
    messages: list[ChatMessage] = Field(min_length=1)
    max_tokens: int | None = Field(default=None, gt=0)
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)


class ChatChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str | None = None


class ChatCompletionResponse(BaseModel):
    model: str
    choices: list[ChatChoice]
    usage: Usage = Field(default_factory=Usage)

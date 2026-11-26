from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=64)


class Source(BaseModel):
    id: int
    title: str
    url: str | None = None
    snippet: str


class Job(BaseModel):
    id: str
    title: str
    city: str
    language: str  # "fr" | "en" | "bilingual"
    url: str
    summary: str = ""


class GuardrailInfo(BaseModel):
    input_masked: bool = False
    blocked: bool = False


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[Source] = []
    jobs: list[Job] = []
    grounded: bool = False
    guardrail: GuardrailInfo = GuardrailInfo()


class EscalationRequest(BaseModel):
    session_id: str = Field(max_length=64)
    topic: str = Field(default="", max_length=500)


class EscalationResponse(BaseModel):
    ticket_id: str
    message: str

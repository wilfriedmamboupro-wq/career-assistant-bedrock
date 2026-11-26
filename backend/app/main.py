"""FastAPI app. Runs locally with uvicorn and on AWS Lambda through Mangum."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.assistant import Assistant, AssistantUnavailable
from app.config import Settings, get_settings
from app.guardrails import BedrockGuard, RegexGuard
from app.jobs import JobIndex
from app.retrieval import KnowledgeBaseRetriever, LocalRetriever
from app.schemas import ChatRequest, ChatResponse, EscalationRequest, EscalationResponse
from app.store import DynamoStore, MemoryStore

DISCLAIMER = "Career Assistant — prototype personnel, non affilié à l'entreprise."


@lru_cache
def get_assistant() -> Assistant:
    s = get_settings()
    if s.mode == "offline":
        from app.offline import OfflineLLM

        return Assistant(
            s,
            OfflineLLM(),
            LocalRetriever(s.kb_dir),
            JobIndex.from_file(s.jobs_file),
            RegexGuard(),
            MemoryStore(),
        )

    import boto3
    from botocore.config import Config

    retriever = (
        KnowledgeBaseRetriever(
            boto3.client("bedrock-agent-runtime", region_name=s.aws_region),
            s.knowledge_base_id,
            s.retrieval_top_k,
            s.retrieval_min_score,
        )
        if s.knowledge_base_id
        else LocalRetriever(s.kb_dir)
    )
    guard = (
        BedrockGuard(
            boto3.client("bedrock-runtime", region_name=s.aws_region),
            s.guardrail_id,
            s.guardrail_version,
        )
        if s.guardrail_id
        else RegexGuard()
    )
    store = DynamoStore(
        boto3.resource("dynamodb", region_name=s.aws_region).Table(s.table_name),
        s.session_ttl_days,
    )
    llm = boto3.client(
        "bedrock-runtime",
        region_name=s.aws_region,
        config=Config(read_timeout=25, retries={"max_attempts": 3, "mode": "adaptive"}),
    )
    return Assistant(s, llm, retriever, JobIndex.from_file(s.jobs_file), guard, store)


AssistantDep = Annotated[Assistant, Depends(get_assistant)]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Career Assistant API", version="0.1.0", description=DISCLAIMER)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["content-type"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "mode": settings.mode, "disclaimer": DISCLAIMER}

    @app.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest, assistant: AssistantDep) -> ChatResponse:
        try:
            return assistant.chat(req.message, req.session_id)
        except AssistantUnavailable as exc:
            raise HTTPException(status_code=503, detail="Model temporarily unavailable") from exc

    @app.post("/escalations", response_model=EscalationResponse, status_code=201)
    def escalate(req: EscalationRequest, assistant: AssistantDep) -> EscalationResponse:
        topic = assistant.guard.check(req.topic, "INPUT").text if req.topic else ""
        ticket = assistant.store.create_ticket(req.session_id, topic)
        return EscalationResponse(
            ticket_id=ticket,
            message=(
                f"Demande n° {ticket} transmise (démo : ticket fictif, aucun recruteur réel "
                f"n'est notifié). / Request {ticket} logged (demo only, no real recruiter "
                "is notified)."
            ),
        )

    return app


app = create_app()
# CloudFront forwards /api/* to API Gateway; strip the prefix so routes stay /chat, /health...
handler = Mangum(app, lifespan="off", api_gateway_base_path="/api")

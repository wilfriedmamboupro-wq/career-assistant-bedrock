"""Runtime configuration, read from environment variables prefixed with CA_."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CA_", env_file=".env", extra="ignore")

    # "aws"     -> Bedrock (Converse + Knowledge Base + Guardrails) and DynamoDB
    # "offline" -> no cloud calls: local markdown search, regex PII masking,
    #              in-memory store, canned LLM. Used for UI work and tests.
    mode: Literal["aws", "offline"] = "offline"

    aws_region: str = "ca-central-1"
    # Cheapest text model in ca-central-1, through the Canada-only inference profile
    # (inference stays in Canadian regions). Quality option: ca.anthropic.claude-haiku-5-5
    model_id: str = "ca.amazon.nova-lite-v1:0"
    max_tokens: int = 1024

    knowledge_base_id: str = ""
    retrieval_top_k: int = 5
    retrieval_min_score: float = 0.35

    guardrail_id: str = ""
    guardrail_version: str = "DRAFT"

    table_name: str = "career-assistant"
    session_ttl_days: int = 7
    history_max_messages: int = 10

    jobs_file: Path = DATA_DIR / "jobs.json"
    kb_dir: Path = DATA_DIR / "kb"

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()

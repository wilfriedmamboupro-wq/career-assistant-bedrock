from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.assistant import Assistant
from app.config import Settings
from app.guardrails import RegexGuard
from app.jobs import JobIndex
from app.main import create_app, get_assistant
from app.retrieval import LocalRetriever
from app.store import MemoryStore

FIXTURES = Path(__file__).parent / "fixtures"


def converse_reply(content, stop="end_turn", tokens=(100, 20)):
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop,
        "usage": {"inputTokens": tokens[0], "outputTokens": tokens[1]},
    }


def text_reply(text):
    return converse_reply([{"text": text}])


def tool_reply(**args):
    call = {"toolUse": {"toolUseId": "tooluse_1", "name": "search_jobs", "input": args}}
    return converse_reply([call], stop="tool_use")


class ScriptedLLM:
    """Returns queued Converse responses in order and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def last_user_text(call) -> str:
    return call["messages"][-1]["content"][0]["text"]


@pytest.fixture
def settings():
    return Settings(mode="offline", jobs_file=FIXTURES / "jobs.json", kb_dir=FIXTURES / "kb")


@pytest.fixture
def make_assistant(settings):
    def _make(llm, guard=None, store=None):
        return Assistant(
            settings,
            llm,
            LocalRetriever(settings.kb_dir),
            JobIndex.from_file(settings.jobs_file),
            guard or RegexGuard(),
            store or MemoryStore(),
        )

    return _make


@pytest.fixture
def client_for(settings):
    def _client(assistant):
        app = create_app(settings)
        app.dependency_overrides[get_assistant] = lambda: assistant
        return TestClient(app)

    return _client

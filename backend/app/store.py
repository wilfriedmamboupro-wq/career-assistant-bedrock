"""Conversation history and escalation tickets.

Only guardrail-processed (PII-masked) text is stored, and every item expires
after `ttl_days` through DynamoDB TTL.
"""

import time
import uuid
from typing import Protocol


class Store(Protocol):
    def get_history(self, session_id: str) -> list[dict]: ...
    def save_history(self, session_id: str, messages: list[dict]) -> None: ...
    def create_ticket(self, session_id: str, topic: str) -> str: ...


class DynamoStore:
    def __init__(self, table, ttl_days: int):
        self._table = table  # boto3 dynamodb Table resource
        self._ttl_seconds = ttl_days * 86400

    def _expires(self) -> int:
        return int(time.time()) + self._ttl_seconds

    def get_history(self, session_id: str) -> list[dict]:
        item = self._table.get_item(Key={"pk": f"session#{session_id}"}).get("Item")
        return item["messages"] if item else []

    def save_history(self, session_id: str, messages: list[dict]) -> None:
        self._table.put_item(
            Item={"pk": f"session#{session_id}", "messages": messages, "ttl": self._expires()}
        )

    def create_ticket(self, session_id: str, topic: str) -> str:
        ticket_id = uuid.uuid4().hex[:8]
        self._table.put_item(
            Item={
                "pk": f"ticket#{ticket_id}",
                "session_id": session_id,
                "topic": topic,
                "status": "open",
                "created_at": int(time.time()),
                "ttl": self._expires(),
            }
        )
        return ticket_id


class MemoryStore:
    def __init__(self):
        self.sessions: dict[str, list[dict]] = {}
        self.tickets: dict[str, dict] = {}

    def get_history(self, session_id: str) -> list[dict]:
        return list(self.sessions.get(session_id, []))

    def save_history(self, session_id: str, messages: list[dict]) -> None:
        self.sessions[session_id] = messages

    def create_ticket(self, session_id: str, topic: str) -> str:
        ticket_id = uuid.uuid4().hex[:8]
        self.tickets[ticket_id] = {"session_id": session_id, "topic": topic}
        return ticket_id

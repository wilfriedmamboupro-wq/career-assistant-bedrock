"""Input/output filtering.

aws mode: Bedrock Guardrails via ApplyGuardrail (PII anonymization + denied topics),
independent of the model call so the same guardrail covers any model.
offline mode: regex masking of the most common Canadian PII, as a stand-in.
"""

import re
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class GuardResult:
    text: str
    masked: bool = False
    blocked: bool = False


class Guard(Protocol):
    def check(self, text: str, source: Literal["INPUT", "OUTPUT"]) -> GuardResult: ...


class BedrockGuard:
    def __init__(self, client, guardrail_id: str, version: str):
        self._client = client  # boto3 "bedrock-runtime"
        self._id = guardrail_id
        self._version = version

    def check(self, text: str, source: Literal["INPUT", "OUTPUT"]) -> GuardResult:
        resp = self._client.apply_guardrail(
            guardrailIdentifier=self._id,
            guardrailVersion=self._version,
            source=source,
            content=[{"text": {"text": text}}],
        )
        if resp.get("action") != "GUARDRAIL_INTERVENED":
            return GuardResult(text=text)
        out = "".join(o.get("text", "") for o in resp.get("outputs", [])) or text
        blocked = _has_blocked_action(resp.get("assessments", []))
        return GuardResult(text=out, masked=not blocked, blocked=blocked)


def _has_blocked_action(node) -> bool:
    """True if any policy in the assessments BLOCKED (vs. only ANONYMIZED PII)."""
    if isinstance(node, dict):
        if node.get("action") == "BLOCKED":
            return True
        return any(_has_blocked_action(v) for v in node.values())
    if isinstance(node, list):
        return any(_has_blocked_action(v) for v in node)
    return False


_PII_PATTERNS = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("PHONE", re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")),
    ("SIN", re.compile(r"\b\d{3}[\s-]?\d{3}[\s-]?\d{3}\b")),  # NAS / Social Insurance Number
]


class RegexGuard:
    def check(self, text: str, source: Literal["INPUT", "OUTPUT"]) -> GuardResult:
        masked = text
        for label, pattern in _PII_PATTERNS:
            masked = pattern.sub(f"{{{label}}}", masked)
        return GuardResult(text=masked, masked=masked != text)

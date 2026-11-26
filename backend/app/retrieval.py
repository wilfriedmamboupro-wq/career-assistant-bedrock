"""Retrieval of public career content: Bedrock Knowledge Base, or local markdown in offline mode."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.jobs import _norm


@dataclass
class Passage:
    title: str
    url: str | None
    text: str
    score: float


class Retriever(Protocol):
    def retrieve(self, query: str) -> list[Passage]: ...


class KnowledgeBaseRetriever:
    """Bedrock Knowledge Base (S3 Vectors). Title/URL come from <doc>.metadata.json files."""

    def __init__(self, client, kb_id: str, top_k: int, min_score: float):
        self._client = client  # boto3 "bedrock-agent-runtime"
        self._kb_id = kb_id
        self._top_k = top_k
        self._min_score = min_score

    def retrieve(self, query: str) -> list[Passage]:
        resp = self._client.retrieve(
            knowledgeBaseId=self._kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": self._top_k}},
        )
        passages = []
        for r in resp.get("retrievalResults", []):
            score = r.get("score", 0.0)
            if score < self._min_score:
                continue
            meta = r.get("metadata", {})
            uri = r.get("location", {}).get("s3Location", {}).get("uri", "")
            passages.append(
                Passage(
                    title=meta.get("title") or uri.rsplit("/", 1)[-1],
                    url=meta.get("source_url"),
                    text=r["content"]["text"],
                    score=score,
                )
            )
        return passages


class LocalRetriever:
    """Keyword overlap over data/kb/*.md — good enough to develop the UI without AWS.

    Each file may start with front matter lines `title: ...` and `source_url: ...`.
    """

    def __init__(self, kb_dir: Path, top_k: int = 3):
        self._top_k = top_k
        self._docs: list[tuple[str, str | None, str]] = []
        for path in sorted(kb_dir.glob("*.md")) if kb_dir.exists() else []:
            raw = path.read_text(encoding="utf-8")
            title = _front(raw, "title") or path.stem
            self._docs.append((title, _front(raw, "source_url"), raw))

    def retrieve(self, query: str) -> list[Passage]:
        terms = {w for w in re.findall(r"\w{4,}", _norm(query))}
        if not terms:
            return []
        scored = []
        for title, url, text in self._docs:
            words = set(re.findall(r"\w{4,}", _norm(text)))
            score = len(terms & words) / len(terms)
            if score > 0:
                scored.append(Passage(title=title, url=url, text=text[:1500], score=score))
        scored.sort(key=lambda p: p.score, reverse=True)
        return scored[: self._top_k]


def _front(raw: str, key: str) -> str | None:
    match = re.search(rf"^{key}:\s*(.+)$", raw, re.MULTILINE)
    return match.group(1).strip() if match else None

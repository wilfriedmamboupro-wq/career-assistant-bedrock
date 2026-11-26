"""search_jobs tool: filters a small JSON file of public job postings."""

import json
import re
import unicodedata
from pathlib import Path

from app.schemas import Job

MAX_RESULTS = 5

# Bedrock Converse tool definition. All filters optional; omitted = no filter.
SEARCH_JOBS_TOOL = {
    "toolSpec": {
        "name": "search_jobs",
        "description": (
            "Search the public job postings. Use it whenever the user asks about open "
            "positions, roles, or jobs in a given field or city. Only pass the filters the "
            "user actually mentioned. Technical postings are titled in English: use English "
            "keywords for them (e.g. 'developer', 'AI', 'software'); claims and customer "
            "service postings exist in both languages."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Keywords from the job title or field, e.g. 'data'.",
                    },
                    "city": {"type": "string", "description": "City name, e.g. 'Montréal'."},
                    "language": {
                        "type": "string",
                        "enum": ["fr", "en"],
                        "description": "Posting language, only if the user asked for it.",
                    },
                },
                "required": [],
            }
        },
    }
}


def _norm(text: str) -> str:
    """Lowercase and strip accents so 'Montréal' matches 'montreal'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


class JobIndex:
    def __init__(self, jobs: list[Job]):
        self._jobs = jobs

    @classmethod
    def from_file(cls, path: Path) -> "JobIndex":
        if not path.exists():
            return cls([])
        return cls([Job(**item) for item in json.loads(path.read_text(encoding="utf-8"))])

    def search(
        self, title: str | None = None, city: str | None = None, language: str | None = None
    ) -> list[Job]:
        words = re.findall(r"\w+", _norm(title)) if title else []
        results = []
        for job in self._jobs:
            tokens = re.findall(r"\w+", _norm(f"{job.title} {job.summary}"))
            # prefix match on whole words: "dev" finds "developer", "ai" does not find "claims"
            if words and not all(any(t.startswith(w) for t in tokens) for w in words):
                continue
            if city and _norm(city) not in _norm(job.city):
                continue
            if language and job.language not in (language, "bilingual"):
                continue
            results.append(job)
        return results[:MAX_RESULTS]

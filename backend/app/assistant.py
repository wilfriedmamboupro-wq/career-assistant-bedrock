"""One chat turn: guardrail in -> retrieve -> LLM (+ search_jobs tool) -> guardrail out.

The model is called through the Bedrock Converse API, so switching between
Amazon Nova and Claude is a configuration change (CA_MODEL_ID), not a code change.
"""

import json
import re
import time
import uuid

from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings
from app.guardrails import Guard
from app.jobs import SEARCH_JOBS_TOOL, JobIndex
from app.metrics import emit
from app.prompts import SYSTEM_PROMPT, build_user_turn, detect_language, is_job_search
from app.retrieval import Retriever
from app.schemas import ChatResponse, GuardrailInfo, Job, Source
from app.store import Store

MAX_TOOL_ROUNDS = 3
RETRYABLE = {
    "ThrottlingException",
    "ServiceUnavailableException",
    "ModelTimeoutException",
    "ModelNotReadyException",
    "InternalServerException",
    "AccessDeniedException",  # model access revoked / not granted: tell the user, log it
}

BLOCKED_ANSWER = (
    "Je ne peux pas répondre à cette demande. Je peux vous aider sur les carrières, les "
    "offres d'emploi et le processus d'embauche. / I can't help with that request, but I "
    "can help with careers, job openings and the hiring process."
)
UNAVAILABLE_ANSWER = (
    "Le service est momentanément indisponible, réessayez dans un instant. / The service "
    "is temporarily unavailable, please try again shortly."
)
# Used when the model returns nothing visible (e.g. only <thinking>): never show an empty bubble
FALLBACK = {
    "fr": {
        "jobs": "Voici les offres correspondantes.",
        "none": "Je ne sais pas d'après les informations publiques disponibles.",
    },
    "en": {
        "jobs": "Here are the matching job openings.",
        "none": "I don't know based on the public information available.",
    },
}

# Small models sometimes leak scaffolding into the visible answer: drop whole blocks,
# unwrap <answer>, and remove any leftover tag.
_LEAKED_BLOCKS = re.compile(r"<(thinking|toolResult|tool_result|sources)>.*?</\1>", re.S | re.I)
_ANY_TAG = re.compile(r"</?[A-Za-z_][^<>\n]{0,40}>")


def _clean(text: str) -> str:
    text = _LEAKED_BLOCKS.sub("", text)
    text = _ANY_TAG.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


class AssistantUnavailable(Exception):
    """Raised when the model provider fails in a way the user should retry later."""


class Assistant:
    def __init__(
        self,
        settings: Settings,
        llm,  # boto3 "bedrock-runtime" client, or a fake exposing .converse()
        retriever: Retriever,
        jobs: JobIndex,
        guard: Guard,
        store: Store,
    ):
        self.s = settings
        self.llm = llm
        self.retriever = retriever
        self.jobs = jobs
        self.guard = guard
        self.store = store

    def chat(self, message: str, session_id: str | None) -> ChatResponse:
        started = time.perf_counter()
        session_id = session_id or uuid.uuid4().hex

        checked = self.guard.check(message, "INPUT")
        info = GuardrailInfo(input_masked=checked.masked, blocked=checked.blocked)
        if checked.blocked:
            emit(blocked=1, latency_ms=_ms(started))
            return ChatResponse(session_id=session_id, answer=BLOCKED_ANSWER, guardrail=info)

        question = checked.text  # PII already masked from here on
        passages = self.retriever.retrieve(question)
        history = self.store.get_history(session_id)
        messages = [*history, _msg("user", build_user_turn(question, passages))]

        # Nova sometimes answers job questions from the sources instead of calling the tool
        # (no job cards). Force a tool call on the first round. Not for Claude: recent
        # Claude models reject a forced tool_choice.
        force_tool = is_job_search(question) and "nova" in self.s.model_id
        answer, jobs, usage = self._run(messages, force_tool=force_tool)
        if not answer:
            answer = FALLBACK[detect_language(question)]["jobs" if jobs else "none"]

        out = self.guard.check(answer, "OUTPUT")
        if out.blocked:
            answer, info.blocked = BLOCKED_ANSWER, True
        else:
            answer = out.text

        answer = _drop_invalid_citations(answer, len(passages))
        sources = _cited_sources(answer, passages)
        grounded = bool(sources or jobs)

        history += [_msg("user", question), _msg("assistant", answer)]
        self.store.save_history(session_id, history[-self.s.history_max_messages :])

        emit(
            latency_ms=_ms(started),
            input_tokens=usage[0],
            output_tokens=usage[1],
            grounded=int(grounded),
            no_answer=int(not grounded),
            pii_masked=int(info.input_masked),
            blocked=int(info.blocked),
        )
        return ChatResponse(
            session_id=session_id,
            answer=answer,
            sources=sources,
            jobs=jobs,
            grounded=grounded,
            guardrail=info,
        )

    def _run(
        self, messages: list[dict], force_tool: bool = False
    ) -> tuple[str, list[Job], tuple[int, int]]:
        """Manual tool loop: few rounds, one local tool."""
        found: list[Job] = []
        tokens_in = tokens_out = 0
        for round_no in range(MAX_TOOL_ROUNDS):
            tool_config: dict = {"tools": [SEARCH_JOBS_TOOL]}
            if force_tool and round_no == 0:
                tool_config["toolChoice"] = {"any": {}}
            try:
                resp = self.llm.converse(
                    modelId=self.s.model_id,
                    system=[{"text": SYSTEM_PROMPT}],
                    messages=messages,
                    toolConfig=tool_config,
                    inferenceConfig={"maxTokens": self.s.max_tokens},
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] in RETRYABLE:
                    raise AssistantUnavailable(str(exc)) from exc
                raise  # ValidationException etc.: our bug, surface it
            except BotoCoreError as exc:  # network, timeouts
                raise AssistantUnavailable(str(exc)) from exc

            tokens_in += resp["usage"]["inputTokens"]
            tokens_out += resp["usage"]["outputTokens"]
            stop = resp["stopReason"]
            content = resp["output"]["message"]["content"]

            if stop in ("guardrail_intervened", "content_filtered"):
                return BLOCKED_ANSWER, found, (tokens_in, tokens_out)

            tool_calls = [b["toolUse"] for b in content if "toolUse" in b]
            if stop != "tool_use" or not tool_calls:
                text = "".join(b["text"] for b in content if "text" in b)
                return _clean(text), found, (tokens_in, tokens_out)

            messages = [*messages, {"role": "assistant", "content": content}]
            results = []
            for call in tool_calls:
                if call["name"] != "search_jobs":
                    results.append(_tool_result(call["toolUseId"], f"Unknown tool {call['name']}"))
                    continue
                hits = self.jobs.search(**_job_args(call["input"]))
                found.extend(h for h in hits if h not in found)
                payload = [h.model_dump(include={"id", "title", "city", "language"}) for h in hits]
                results.append(_tool_result(call["toolUseId"], {"jobs": payload}))
            messages.append({"role": "user", "content": results})

        return UNAVAILABLE_ANSWER, found, (tokens_in, tokens_out)


def _msg(role: str, text: str) -> dict:
    return {"role": role, "content": [{"text": text}]}


def _job_args(raw) -> dict:
    data = raw if isinstance(raw, dict) else json.loads(raw)
    return {k: (data.get(k) or None) for k in ("title", "city", "language")}


def _tool_result(tool_use_id: str, body: dict | str) -> dict:
    if isinstance(body, str):
        return {
            "toolResult": {"toolUseId": tool_use_id, "content": [{"text": body}], "status": "error"}
        }
    return {"toolResult": {"toolUseId": tool_use_id, "content": [{"json": body}]}}


def _drop_invalid_citations(answer: str, n_passages: int) -> str:
    """Remove [n] markers that point to no retrieved passage (small models do this)."""

    def keep(m: re.Match) -> str:
        return m.group(0) if 1 <= int(m.group(1)) <= n_passages else ""

    return re.sub(r" ?\[(\d+)\]", keep, answer)


def _cited_sources(answer: str, passages) -> list[Source]:
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer)})
    return [
        Source(
            id=i,
            title=passages[i - 1].title,
            url=passages[i - 1].url,
            snippet=passages[i - 1].text[:240],
        )
        for i in cited
        if 1 <= i <= len(passages)
    ]


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)

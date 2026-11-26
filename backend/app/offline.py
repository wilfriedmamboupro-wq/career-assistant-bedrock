"""Canned stand-in for Bedrock Converse so the API and widget run with no AWS account."""

import re
import uuid

_JOB_WORDS = re.compile(r"\b(job|jobs|position|opening|poste|postes|offre|offres|emploi)\b", re.I)
_USAGE = {"inputTokens": 0, "outputTokens": 0}


class OfflineLLM:
    def converse(self, *, messages, **_):
        last = messages[-1]["content"][0]
        if "toolResult" in last:
            return _reply("Voici les offres correspondantes (mode hors ligne).")
        text = last["text"]
        if _JOB_WORDS.search(text.split("<question>")[-1]):
            call = {
                "toolUse": {
                    "toolUseId": f"tooluse_{uuid.uuid4().hex[:8]}",
                    "name": "search_jobs",
                    "input": {},
                }
            }
            return {
                "output": {"message": {"role": "assistant", "content": [call]}},
                "stopReason": "tool_use",
                "usage": _USAGE,
            }
        if "[1]" in text:
            return _reply("Réponse hors ligne basée sur la source [1].")
        return _reply("Je ne sais pas d'après les informations publiques disponibles.")


def _reply(text: str) -> dict:
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
        "usage": _USAGE,
    }

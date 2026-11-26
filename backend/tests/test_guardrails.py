from app.guardrails import BedrockGuard, RegexGuard


def test_regex_guard_masks_email_phone_and_sin():
    r = RegexGuard().check("Moi: jean@x.ca, 514-555-1234, NAS 123 456 789", "INPUT")
    assert r.masked and not r.blocked
    assert "jean@x.ca" not in r.text and "555" not in r.text and "456" not in r.text
    assert "{EMAIL}" in r.text and "{PHONE}" in r.text and "{SIN}" in r.text


def test_regex_guard_leaves_clean_text():
    r = RegexGuard().check("Quels sont les avantages sociaux ?", "INPUT")
    assert r.text == "Quels sont les avantages sociaux ?" and not r.masked


class FakeRuntime:
    def __init__(self, resp):
        self.resp = resp

    def apply_guardrail(self, **kwargs):
        self.kwargs = kwargs
        return self.resp


def test_bedrock_guard_anonymized_pii_is_masked_not_blocked():
    rt = FakeRuntime(
        {
            "action": "GUARDRAIL_INTERVENED",
            "outputs": [{"text": "Mon courriel est {EMAIL}"}],
            "assessments": [
                {
                    "sensitiveInformationPolicy": {
                        "piiEntities": [{"type": "EMAIL", "action": "ANONYMIZED"}]
                    }
                }
            ],
        }
    )
    r = BedrockGuard(rt, "gr-1", "1").check("Mon courriel est a@b.ca", "INPUT")
    assert r.masked and not r.blocked and r.text == "Mon courriel est {EMAIL}"
    assert rt.kwargs["source"] == "INPUT" and rt.kwargs["guardrailIdentifier"] == "gr-1"


def test_bedrock_guard_denied_topic_is_blocked():
    rt = FakeRuntime(
        {
            "action": "GUARDRAIL_INTERVENED",
            "outputs": [{"text": "blocked"}],
            "assessments": [
                {"topicPolicy": {"topics": [{"name": "Politics", "action": "BLOCKED"}]}}
            ],
        }
    )
    assert BedrockGuard(rt, "gr-1", "1").check("x", "INPUT").blocked


def test_bedrock_guard_no_intervention():
    r = BedrockGuard(FakeRuntime({"action": "NONE"}), "gr-1", "1").check("ok", "OUTPUT")
    assert r.text == "ok" and not r.masked and not r.blocked

from botocore.exceptions import ClientError

from app.guardrails import GuardResult
from app.store import MemoryStore
from tests.conftest import ScriptedLLM, converse_reply, last_user_text, text_reply, tool_reply


def post(client, message, **extra):
    return client.post("/chat", json={"message": message, **extra})


def test_rag_answer_cites_only_used_sources(make_assistant, client_for):
    llm = ScriptedLLM(text_reply("Le travail est hybride, 2 jours de télétravail [1]."))
    res = post(client_for(make_assistant(llm)), "Est-ce que le télétravail hybride est possible ?")

    body = res.json()
    assert res.status_code == 200
    assert body["grounded"] is True
    assert [s["url"] for s in body["sources"]] == ["https://example.com/careers/hybrid"]
    assert "[1] Mode de travail hybride" in last_user_text(llm.calls[0])


def test_unknown_answer_is_not_grounded(make_assistant, client_for):
    llm = ScriptedLLM(text_reply("Je ne sais pas d'après les informations publiques."))
    body = post(client_for(make_assistant(llm)), "Salaire du PDG ?").json()
    assert body["grounded"] is False and body["sources"] == []


def test_citation_without_matching_source_is_removed(make_assistant, client_for):
    llm = ScriptedLLM(text_reply("Consultez la politique de confidentialité [3]."))
    body = post(client_for(make_assistant(llm)), "Le télétravail hybride ?").json()
    assert body["answer"] == "Consultez la politique de confidentialité."
    assert body["sources"] == []


def test_leaked_scaffolding_is_removed(make_assistant, client_for):
    raw = (
        "<thinking>plan</thinking><answer>Un poste à Toronto.</answer> "
        '<toolResult>{"jobs": []}</toolResult>'
    )
    body = post(client_for(make_assistant(ScriptedLLM(text_reply(raw)))), "Salut").json()
    assert body["answer"] == "Un poste à Toronto."


def test_reply_language_follows_question(make_assistant, client_for):
    llm = ScriptedLLM(text_reply("ok"), text_reply("ok"))
    client = client_for(make_assistant(llm))
    post(client, "How many remote days per week?")
    post(client, "Combien de jours de télétravail ?")
    assert "Reply in English" in last_user_text(llm.calls[0])
    assert "Reply in French" in last_user_text(llm.calls[1])


def test_job_search_tool_round_trip(make_assistant, client_for):
    llm = ScriptedLLM(
        tool_reply(title="python", city="Montréal"),
        text_reply("Voici un poste qui correspond."),
    )
    body = post(client_for(make_assistant(llm)), "Des postes Python à Montréal ?").json()

    assert [j["id"] for j in body["jobs"]] == ["T-001"]
    second = llm.calls[1]["messages"]
    assert second[-2]["role"] == "assistant"
    result = second[-1]["content"][0]["toolResult"]
    assert result["toolUseId"] == "tooluse_1"
    assert result["content"][0]["json"]["jobs"][0]["id"] == "T-001"


def test_unknown_tool_returns_error_result(make_assistant, client_for):
    bad = converse_reply(
        [{"toolUse": {"toolUseId": "t9", "name": "delete_all", "input": {}}}], stop="tool_use"
    )
    llm = ScriptedLLM(bad, text_reply("Désolé."))
    post(client_for(make_assistant(llm)), "x")
    assert llm.calls[1]["messages"][-1]["content"][0]["toolResult"]["status"] == "error"


def test_pii_is_masked_before_model_and_storage(make_assistant, client_for):
    llm, store = ScriptedLLM(text_reply("D'accord.")), MemoryStore()
    client = client_for(make_assistant(llm, store=store))
    body = post(client, "Rappelez-moi au 514-555-1234", session_id="s1").json()

    assert body["guardrail"]["input_masked"] is True
    assert "555-1234" not in last_user_text(llm.calls[0])
    assert "555-1234" not in str(store.sessions["s1"])


def test_blocked_input_never_reaches_model(make_assistant, client_for):
    class BlockAll:
        def check(self, text, source):
            return GuardResult(text=text, blocked=True)

    llm = ScriptedLLM()
    body = post(client_for(make_assistant(llm, guard=BlockAll())), "Pour qui voter ?").json()
    assert body["guardrail"]["blocked"] is True and llm.calls == []


def test_history_is_reused_per_session(make_assistant, client_for):
    llm = ScriptedLLM(text_reply("Bonjour."), text_reply("Encore bonjour."))
    client = client_for(make_assistant(llm))
    sid = post(client, "Salut").json()["session_id"]
    post(client, "Et ensuite ?", session_id=sid)

    second = llm.calls[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[0]["content"][0]["text"] == "Salut"  # history keeps the question, not sources


def test_model_side_filter_returns_polite_message(make_assistant, client_for):
    llm = ScriptedLLM(converse_reply([], stop="content_filtered"))
    body = post(client_for(make_assistant(llm)), "x").json()
    assert "Je ne peux pas" in body["answer"]


def test_throttling_maps_to_503(make_assistant, client_for):
    class Throttled:
        def converse(self, **_):
            err = {"Error": {"Code": "ThrottlingException", "Message": "slow down"}}
            raise ClientError(err, "Converse")

    assert post(client_for(make_assistant(Throttled())), "Bonjour").status_code == 503


def test_escalation_creates_ticket_with_masked_topic(make_assistant, client_for):
    store = MemoryStore()
    res = client_for(make_assistant(ScriptedLLM(), store=store)).post(
        "/escalations", json={"session_id": "s1", "topic": "Écrivez-moi: a@b.ca"}
    )
    assert res.status_code == 201
    assert "a@b.ca" not in store.tickets[res.json()["ticket_id"]]["topic"]


def test_validation_rejects_empty_message(make_assistant, client_for):
    assert post(client_for(make_assistant(ScriptedLLM())), "").status_code == 422


def test_health(make_assistant, client_for):
    body = client_for(make_assistant(ScriptedLLM())).get("/health").json()
    assert body["status"] == "ok" and "non affilié" in body["disclaimer"]


def test_language_detection_on_short_questions():
    from app.prompts import detect_language

    assert detect_language("Y a-t-il un boni annuel ?") == "fr"
    assert detect_language("Faut-il être bilingue ?") == "fr"
    assert detect_language("Is there an annual bonus?") == "en"
    assert detect_language("Any AI jobs in Toronto?") == "en"

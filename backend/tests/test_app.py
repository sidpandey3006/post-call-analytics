import json
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from entities import find_candidates, normalize_entity  # noqa: E402
from main import app  # noqa: E402
from models import FieldDef  # noqa: E402
from normalize import normalize_transcript  # noqa: E402
from postprocess import build_results  # noqa: E402
from questions import FieldError, build_questions  # noqa: E402

client = TestClient(app)

TURNS = {"turns": [
    {"speaker": "agent", "start": 0, "text": "Hi this is Sam."},
    {"speaker": "agent", "start": 3, "text": "The plan is $1,200.50 a year."},
    {"speaker": "customer", "start": 6, "text": "Email me at Dana@Acme.com or call (415) 555-0177. Follow up on 12 Oct 2026."},
]}


def test_normalize_merges_and_numbers():
    state, w = normalize_transcript(TURNS)
    assert [t["i"] for t in state["turns"]] == [1, 2]
    assert state["turns"][0]["text"].endswith("a year.")
    assert w == []


def test_normalize_assemblyai_ms():
    state, _ = normalize_transcript({"utterances": [{"speaker": "A", "text": "hello", "start": 1500, "end": 2000}]})
    assert state["turns"][0]["start"] == 1.5


def test_normalize_deepgram_utterances():
    state, _ = normalize_transcript({"results": {"utterances": [{"speaker": 0, "transcript": "hi", "start": 0.1, "end": 1}]}})
    assert state["turns"][0]["text"] == "hi"


def test_normalize_errors():
    with pytest.raises(ValueError):
        normalize_transcript({"foo": 1})
    with pytest.raises(ValueError):
        normalize_transcript({"turns": [{"speaker": "agent", "text": "  "}]})


def test_candidates_and_normalization():
    text = "Dana@Acme.com, (415) 555-0177, $1,200.50, 12 Oct 2026"
    assert find_candidates("email", text) == ["Dana@Acme.com"]
    assert "(415) 555-0177" in find_candidates("phone", text)
    assert "$1,200.50" in find_candidates("amount", text)
    assert find_candidates("date", text) == ["12 Oct 2026"]
    assert normalize_entity("email", "Dana@Acme.com") == "dana@acme.com"
    assert normalize_entity("phone", "(415) 555-0177", region="US") == "+14155550177"
    assert normalize_entity("amount", "$1,200.50") == {"amount": "1200.50", "currency": "USD"}
    assert normalize_entity("date", "12 Oct 2026") == "2026-10-12"


def test_build_questions():
    fields = [
        FieldDef(id="a", kind="noul", instructions="q"),
        FieldDef(id="b", kind="choice", instructions="q", criteria={"x": "d", "y": None}),
        FieldDef(id="c", kind="score", instructions="q", levels=["l", "h"]),
        FieldDef(id="e", kind="entity", entity_type="email", instructions="which?"),
    ]
    qs, cands = build_questions(fields, "x@y.com")
    assert qs["c"]["criteria"] == ["l", "h"]
    assert list(qs["e"]["criteria"]) == ["x@y.com", "none"]
    assert cands["e"] == ["x@y.com"]
    with pytest.raises(FieldError):
        build_questions([FieldDef(id="b", kind="choice", instructions="q", criteria={"x": "d"})], "")
    with pytest.raises(FieldError):
        build_questions([fields[0], fields[0]], "")


def test_postprocess_flags():
    fields = [
        FieldDef(id="n", kind="noul", instructions="q"),
        FieldDef(id="c", kind="choice", instructions="q", criteria={"x": None, "y": None}),
        FieldDef(id="e", kind="entity", entity_type="email", instructions="q"),
    ]
    answers = {"n": {"noul": 0.5}, "c": {"choice": "x", "confidence": 0.4, "probabilities": {}},
               "e": {"choice": "a@b.com", "confidence": 0.95}}
    res, flags = build_results(fields, answers, {"e": ["a@b.com"]})
    assert res[0].needs_review and res[1].needs_review and not res[2].needs_review
    assert res[2].normalized == "a@b.com"
    assert len(flags) == 2


def _payload():
    return {"api_key": "sk-secret", "transcript": TURNS, "fields": [
        {"id": "urgent", "kind": "noul", "instructions": "Is it urgent?"},
        {"id": "email", "kind": "entity", "entity_type": "email", "instructions": "Customer email?"},
    ]}


@respx.mock
def test_analyze_ok_and_key_not_in_response():
    route = respx.post("https://api.typesafe.ai/v1/systemone").mock(return_value=httpx.Response(200, json={
        "model": "jev-1", "answers": {"urgent": {"type": "noul", "noul": 0.9},
                                      "email": {"type": "choice", "choice": "Dana@Acme.com", "confidence": 0.99, "probabilities": {}}},
        "usage": {"input_tokens": 10, "output_tokens": 2}}))
    r = client.post("/api/analyze", json=_payload())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["results"][1]["normalized"] == "dana@acme.com"
    assert d["usage"]["input_tokens"] == 10
    assert "sk-secret" not in r.text
    assert route.calls[0].request.headers["authorization"] == "Bearer sk-secret"
    assert route.calls[0].request.content and json.loads(route.calls[0].request.content)["model"] == "jev-latest"


@respx.mock
def test_analyze_401_mapped():
    respx.post("https://api.typesafe.ai/v1/systemone").mock(return_value=httpx.Response(401, json={"error": "bad"}))
    r = client.post("/api/analyze", json=_payload())
    assert r.status_code == 401 and "API key" in r.json()["detail"]


def test_analyze_bad_transcript():
    p = _payload()
    p["transcript"] = {"nope": 1}
    assert client.post("/api/analyze", json=p).status_code == 400


def test_templates_valid():
    for name in ("sales", "loan"):
        fields = [FieldDef(**f) for f in client.get(f"/api/templates/{name}").json()]
        qs, _ = build_questions(fields, "a@b.com 12 Oct 2026 $5 +14155550177")
        assert len(qs) == len(fields)
    assert client.get("/api/templates/nope").status_code == 404


@respx.mock
def test_microsoft_ok_no_confidence():
    url = 'https://res.services.ai.azure.com/providers/microsoft/v1/systemone'
    route = respx.post(url).mock(return_value=httpx.Response(200, json={'model': 'microsoft-decision-1', 'answers': {'urgent': {'type': 'noul', 'noul': 0.8}, 'email': {'type': 'choice', 'choice': 'a@b.com', 'probabilities': {'a@b.com': 0.9, 'none': 0.1}}}}))
    p = _payload(); p.update(provider='microsoft', endpoint='https://res.services.ai.azure.com', model='my-deploy')
    r = client.post('/api/analyze', json=p)
    assert r.status_code == 200, r.text
    assert r.json()['results'][1]['confidence'] == 0.9
    h = route.calls[0].request.headers
    assert h['api-key'] == 'sk-secret' and 'authorization' not in h
    assert json.loads(route.calls[0].request.content)['model'] == 'my-deploy'


def test_microsoft_rejects_non_azure_host():
    p = _payload(); p.update(provider='microsoft', endpoint='https://evil.example.com', model='d')
    assert client.post('/api/analyze', json=p).status_code == 400



GEN_URL = "https://res.services.ai.azure.com/openai/deployments/gpt-4o/chat/completions"


def _gen_payload():
    return {"description": "Outbound loan reminder calls to verify the borrower and get a promise to pay",
            "endpoint": "https://res.services.ai.azure.com", "api_key": "sk-secret", "chat_deployment": "gpt-4o"}


def _chat(fields):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"fields": fields})}}], "usage": {"total_tokens": 5}})


@respx.mock
def test_generate_ok_and_rejects_invalid():
    route = respx.post(GEN_URL).mock(return_value=_chat([
        {"id": "ptp", "kind": "noul", "instructions": "Customer promises to pay.", "options": [], "levels": [], "entity_type": "none"},
        {"id": "reason", "kind": "choice", "instructions": "Reason?", "options": [{"key": "a", "description": "x"}], "levels": [], "entity_type": "none"},
        {"id": "ptp_date", "kind": "entity", "instructions": "Date?", "options": [], "levels": [], "entity_type": "date"},
    ]))
    r = client.post("/api/generate-fields", json=_gen_payload())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mode"] == "generated" and [f["id"] for f in d["fields"]] == ["ptp", "ptp_date"]
    assert d["rejected"][0]["id"] == "reason"
    assert "sk-secret" not in r.text
    req = route.calls[0].request
    assert req.headers["api-key"] == "sk-secret" and "api-version=2024-10-21" in str(req.url)
    assert json.loads(req.content)["response_format"]["json_schema"]["strict"] is True


@respx.mock
def test_generate_all_invalid_422():
    respx.post(GEN_URL).mock(return_value=_chat([{"id": "x", "kind": "score", "instructions": "q", "options": [], "levels": ["one"], "entity_type": "none"}]))
    assert client.post("/api/generate-fields", json=_gen_payload()).status_code == 422


def test_generate_rejects_bad_host_and_deployment():
    p = _gen_payload(); p["endpoint"] = "https://evil.example.com"
    assert client.post("/api/generate-fields", json=p).status_code == 400
    p = _gen_payload(); p["chat_deployment"] = "../x?y"
    assert client.post("/api/generate-fields", json=p).status_code == 400


def test_generate_suggestions_without_credentials():
    r = client.post("/api/generate-fields", json={"description": "collections calls for overdue payment reminders"})
    d = r.json()
    assert d["mode"] == "suggestions" and d["matches"][0]["name"] == "collections"


def test_library_templates_valid():
    from generator import LIBRARY
    from models import FieldDef
    from questions import build_questions
    for t in json.loads(LIBRARY.read_text(encoding="utf-8")):
        build_questions([FieldDef(**f) for f in t["fields"]], "")


def test_every_scenario_has_two_entity_fields():
    data = json.loads((Path(__file__).parent.parent / "templates" / "scenarios.json").read_text(encoding="utf-8"))
    for s in data:
        assert sum(f["kind"] == "entity" for f in s["fields"]) >= 2, s["name"]


def test_scenario_samples_have_no_warnings():
    data = json.loads((Path(__file__).parent.parent / "templates" / "scenarios.json").read_text(encoding="utf-8"))
    for s in data:
        _, warns = normalize_transcript(s["sample"])
        assert warns == [], (s["name"], warns)


def test_scenarios_valid_and_samples_support_entities():
    from entities import find_candidates
    from models import FieldDef
    from normalize import normalize_transcript, transcript_text
    from questions import build_questions
    d = client.get("/api/scenarios").json()
    assert len(d) == 9
    for s in d:
        fields = [FieldDef(**f) for f in s["fields"]]
        assert len({f.id for f in fields}) == len(fields), s["name"]
        state, _ = normalize_transcript(s["sample"], None)
        text = transcript_text(state)
        build_questions(fields, text)
        for f in fields:
            if f.kind == "entity":
                candidates = find_candidates(f.entity_type, text, f.pattern)
                if s["name"] != "loan_entity_extraction":
                    assert candidates, f"{s['name']}:{f.id} has no candidate in sample"


def test_parse_sample():
    from generator import parse_sample
    s = parse_sample('{"sample_transcript":[{"speaker":"agent","text":"Hi"},{"speaker":"customer","text":"Hello"},{"speaker":"bot","text":"x"}]}')
    assert len(s['turns']) == 2 and normalize_transcript(s)[1] == []
    assert parse_sample('not json') is None



def test_library_templates_have_samples():
    lib = json.loads((Path(__file__).parent.parent / 'templates' / 'library.json').read_text(encoding='utf-8'))
    for t in lib:
        assert t.get('sample'), t['name']
        assert normalize_transcript(t['sample'])[1] == []



def test_id_and_name_entities():
    t = 'Hi, my name is Priya Shah. ID is AB123456 and claim CL-998877. I am sorry about that.'
    assert find_candidates('name', t) == ['Priya Shah']
    assert 'AB123456' in find_candidates('id', t)
    assert find_candidates('id', t, r'CL-\d+') == ['CL-998877']
    assert normalize_entity('id', ' AB123456 ') == 'AB123456'
    f = FieldDef(id='x', kind='entity', instructions='q', entity_type='id', pattern='(a+)+')
    with pytest.raises(FieldError):
        build_questions([f], t)


def _extraction_scenario():
    return next(s for s in client.get("/api/scenarios").json() if s["name"] == "loan_entity_extraction")


def test_text_candidates_are_verbatim_and_support_bare_responses():
    text = "My name is Arjun Verma.\nBusiness.\nI work for Example Services.\nLucknow, Uttar Pradesh."
    candidates = find_candidates("text", text)
    assert {"Arjun Verma", "Business", "Example Services", "Lucknow, Uttar Pradesh"} <= set(candidates)
    assert all(c in text for c in candidates)
    assert find_candidates("text", "The EMI is Rs 2,657.", r"Rs ([\d,]+)") == ["2,657"]
    assert normalize_entity("text", " Business ") == "Business"
    with pytest.raises(FieldError):
        build_questions([FieldDef(id="x", kind="entity", entity_type="text", instructions="q", pattern="(")], text)


@respx.mock
def test_loan_extraction_end_to_end():
    scenario = _extraction_scenario()
    fields = [FieldDef(**f) for f in scenario["fields"]]
    state, _ = normalize_transcript(scenario["sample"])
    from normalize import transcript_text
    _, candidates = build_questions(fields, transcript_text(state))
    selected = {
        "greetings_end": "Yes", "bajaj_introduction": "Yes",
        "customer_name": "Arjun Verma", "customer_dob": "01/01/1992",
        "pan_card_digits": "64 1 G", "profession": "Business",
        "current_pincode": "271502", "current_city": "Colonymarket, Uttar Pradesh",
        "loan_amount": "Rs 50,000", "loan_rate": "31% reducing",
        "loan_tenure": "35 months", "loan_emi": "2657",
        "loan_installments": "35", "loan_processing_fee": "2127",
    }
    for fid, value in selected.items():
        if fid in candidates:
            assert value in candidates[fid], (fid, candidates[fid])
    answers = {f.id: {"choice": selected.get(f.id, "none"), "confidence": 0.99}
               for f in fields if f.kind == "choice" or candidates.get(f.id)}
    route = respx.post("https://res.services.ai.azure.com/providers/microsoft/v1/systemone").mock(
        return_value=httpx.Response(200, json={"answers": answers}))
    response = client.post("/api/analyze", json={
        "api_key": "sk-secret", "provider": "microsoft",
        "endpoint": "https://res.services.ai.azure.com", "model": "Decision-1",
        "fields": scenario["fields"], "transcript": scenario["sample"],
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["structured_output"] == {
        "Greetings_end": "Yes", "Bajaj_Introduction": "Yes",
        "Customer_Details": {
            "Name": "Arjun Verma", "DOB": "01/01/1992", "PAN_card_digits": "64 1 G",
            "Profession": "Business", "Company": "", "Years of Experience": "", "Salary": "",
        },
        "Current_Address": {"Pincode": "271502", "City": "Colonymarket, Uttar Pradesh"},
        "Permanent_Address": {"Pincode": "", "City": ""},
        "Loan": {"Amount": 50000, "Rate": "31% reducing", "Tenure": "35 months",
                 "EMI": 2657, "number of installments": 35, "processing fee": 2127},
    }
    assert len(data["results"]) == len(fields)
    assert data["flags"] == []
    assert "output_path" not in route.calls[0].request.content.decode()
    assert "sk-secret" not in response.text


def test_extraction_alternative_wording():
    from normalize import transcript_text
    fields = [FieldDef(**f) for f in _extraction_scenario()["fields"]]
    state, _ = normalize_transcript({"turns": [
        {"speaker": "agent", "text": "Your full name?"},
        {"speaker": "customer", "text": "Meera Sharma."},
        {"speaker": "agent", "text": "Occupation and employer?"},
        {"speaker": "customer", "text": "Software engineer. I work at Example Technologies. I have been working for 8 years."},
        {"speaker": "agent", "text": "Current city and PIN?"},
        {"speaker": "customer", "text": "Pune, Maharashtra. 411001."},
        {"speaker": "agent", "text": "The fee is 1,234 rupees and you pay 2400 every month in 24 installments."},
    ]})
    _, c = build_questions(fields, transcript_text(state))
    assert "Meera Sharma" in c["customer_name"]
    assert "Software engineer" in c["profession"]
    assert "Example Technologies" in c["company"]
    assert "8 years" in c["years_experience"]
    assert "Pune, Maharashtra" in c["current_city"]
    assert "411001" in c["current_pincode"]
    assert "1,234" in c["loan_processing_fee"]
    assert "2400" in c["loan_emi"]
    assert "24" in c["loan_installments"]


def test_output_paths_and_unsupported_entities():
    from postprocess import build_structured_output
    f = FieldDef(id="name", kind="entity", entity_type="text", instructions="q", output_path=["Customer", "Name"])
    results, flags = build_results([f], {"name": {"choice": "invented", "confidence": 1}}, {"name": ["Arjun"]})
    assert flags and results[0].value is None
    assert build_structured_output([f], results) == {"Customer": {"Name": ""}}
    results, flags = build_results([f], {}, {"name": ["Arjun"]})
    assert flags and results[0].review_reason == "No answer returned"
    assert build_structured_output([], []) is None
    duplicate = f.model_copy(update={"id": "other"})
    with pytest.raises(FieldError, match="conflicting output path"):
        build_questions([f, duplicate], "")
    parent = f.model_copy(update={"id": "other", "output_path": ["Customer"]})
    with pytest.raises(FieldError, match="conflicting output path"):
        build_questions([f, parent], "")


def test_numeric_output_and_missing_values():
    from postprocess import build_structured_output
    f = FieldDef(id="fee", kind="entity", entity_type="text", instructions="q",
                 output_path=["Loan", "processing fee"], output_type="number")
    results, _ = build_results([f], {"fee": {"choice": "2,127.50", "confidence": 0.99}}, {"fee": ["2,127.50"]})
    assert build_structured_output([f], results) == {"Loan": {"processing fee": 2127.5}}
    results, _ = build_results([f], {}, {"fee": []})
    assert build_structured_output([f], results) == {"Loan": {"processing fee": ""}}
    results, _ = build_results([f], {"fee": {"choice": "not numeric", "confidence": 0.99}}, {"fee": ["not numeric"]})
    with pytest.raises(ValueError, match="cannot be exported as a number"):
        build_structured_output([f], results)

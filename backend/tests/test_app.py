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


import json
import sys
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from models import FieldDef
from normalize import normalize_transcript, transcript_text
from output_transforms import transform_output
from postprocess import build_results, build_structured_output
from questions import FieldError, build_questions, choice_option_names

client = TestClient(app)
URL = "https://res.services.ai.azure.com/providers/microsoft/v1/systemone"


def scenario():
    return next(s for s in client.get("/api/scenarios").json() if s["name"] == "bharosa_bank_loan_sales")


def answers_for_sample(s):
    raw_numbers = {
        "years_experience": "8 years", "salary": "Rs 85,000", "turnover": "Rs 12 lakh",
        "loan_amount": "Rs 3.5 lakh", "loan_rate": "18%", "loan_tenure": "36 months",
        "loan_emi": "Rs 12,653", "processing_fee": "Rs 3,500",
        "actual_interested_amount": "Rs 3.5 lakh", "fpr_amount": "Rs 10,000",
        "foreclosure_charge": "2%", "bpi": "Rs 1,234",
    }
    answers = {}
    for f in s["fields"]:
        if f.get("source_field"):
            continue
        value = s["sample_output"]
        for key in f["output_path"]:
            value = value[key]
        answers[f["id"]] = {"choice": raw_numbers.get(f["id"], value), "confidence": 0.99}
    return answers


def test_bharosa_complete_schema_and_candidate_coverage():
    s = scenario()
    assert s["title"] == "Bharosa Bank Loan Sales"
    assert "text" not in s["sample"]
    assert len(s["sample"]["turns"]) == 20
    assert all(set(turn) == {"speaker", "text"} for turn in s["sample"]["turns"])
    fields = [FieldDef(**f) for f in s["fields"]]
    state, warnings = normalize_transcript(s["sample"])
    assert state["turns"][0]["speaker"] == "spk2"
    assert state["turns"][1]["speaker"] == "spk1"
    assert state["language"] == "en-IN" and state["direction"] == "outbound"
    assert any("roles" in w for w in warnings)
    questions, candidates = build_questions(fields, transcript_text(state))
    for question in questions.values():
        if question["type"] == "choice":
            assert all(key.strip() for key in question["criteria"])
    for f in fields:
        if f.source_field:
            assert f.id not in questions
        elif f.kind == "entity":
            assert answers_for_sample(s)[f.id]["choice"] in candidates[f.id], (f.id, candidates[f.id])

    def paths(value, prefix=()):
        return {p for k, v in value.items()
                for p in (paths(v, (*prefix, k)) if isinstance(v, dict) else {(*prefix, k)})}

    assert paths(s["sample_output"]) == {tuple(f.output_path) for f in fields}
    assert len(fields) == 53


@respx.mock
def test_bharosa_end_to_end_matches_reference_json():
    s = scenario()
    route = respx.post(URL).mock(return_value=httpx.Response(200, json={"answers": answers_for_sample(s)}))
    response = client.post("/api/analyze", json={
        "api_key": "test-key", "provider": "microsoft",
        "endpoint": "https://res.services.ai.azure.com", "model": "Decision-1",
        "transcript": s["sample"], "fields": s["fields"],
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["structured_output"] == s["sample_output"]
    assert data["flags"] == []
    assert len(data["results"]) == len(s["fields"])
    request = json.loads(route.calls[0].request.content)
    assert "customer_name" not in request["questions"]
    assert "customer_name_extracted" in request["questions"]
    assert request["state"]["turns"][0]["speaker"] == "spk2"
    assert "test-key" not in response.text


def test_bharosa_missing_values_use_exact_types():
    fields = [FieldDef(**f) for f in scenario()["fields"]]
    answers = {f.id: {"choice": "none" if f.kind == "entity" else "", "confidence": 0.99}
               for f in fields if not f.source_field}
    results, _ = build_results(fields, answers, {})
    output = build_structured_output(fields, results)
    for f in fields:
        value = output
        for key in f.output_path:
            value = value[key]
        assert value == (None if f.output_type == "number" else ""), f.id
    assert output["Customer_Details"]["PAN_card_digits"] == ""


@pytest.mark.parametrize(("value", "transform", "expected"), [
    ("APKPP6076L", "pan_last_four", "076L"),
    ("076l", "pan_last_four", "076L"),
    ("05/08/1991", "date_dmy", "05/08/1991"),
    ("1991-08-05", "date_dmy", "05/08/1991"),
    ("5 August 1991", "date_dmy", "05/08/1991"),
    ("०५/०८/१९९१", "date_dmy", "05/08/1991"),
    ("Rs 3.5 lakh", "number", 350000),
    ("Rs 12 lakh", "number", 1200000),
    ("INR 1.2 crore", "number", 12000000),
    ("₹८५,०००", "number", 85000),
    ("8 years", "number", 8),
    ("3 years", "months", 36),
    ("1.5 years", "months", 18),
    ("36 months", "months", 36),
    ("18%", "percent", "18%"),
    ("2%", "number", 2),
])
def test_bharosa_output_transforms(value, transform, expected):
    assert transform_output(value, transform) == expected


@pytest.mark.parametrize(("value", "transform"), [
    ("6076", "pan_last_four"), ("31/02/1991", "date_dmy"),
    ("August 1991", "date_dmy"), ("tomorrow", "date_dmy"),
    ("three lakh", "number"), ("0.1 years", "months"),
    ("नौकरी", "english_text"), ("अर्जुन", "roman_text"),
])
def test_unsupported_conversions_are_explicit(value, transform):
    with pytest.raises(ValueError):
        transform_output(value, transform)


def test_unsupported_translation_keeps_source_and_flags_derived_output():
    fields = [
        FieldDef(id="raw", kind="entity", entity_type="text", instructions="Occupation",
                 output_path=["Customer_Details", "Occupation_extracted"]),
        FieldDef(id="english", kind="entity", entity_type="text", instructions="English occupation",
                 source_field="raw", output_transform="english_text",
                 output_path=["Customer_Details", "Occupation"]),
    ]
    results, flags = build_results(fields, {"raw": {"choice": "नौकरी", "confidence": 0.99}},
                                   {"raw": ["नौकरी"]}, language="hi-IN")
    assert build_structured_output(fields, results) == {
        "Customer_Details": {"Occupation_extracted": "नौकरी", "Occupation": ""}
    }
    assert len(flags) == 1 and "Translation is unsupported" in flags[0]
    with pytest.raises(ValueError, match="Translation"):
        transform_output("naukri", "english_text", language="hi-IN")


def test_derived_fields_require_an_earlier_entity():
    base = FieldDef(id="raw", kind="entity", entity_type="text", instructions="q")
    derived = FieldDef(id="derived", kind="entity", entity_type="text", instructions="q", source_field="raw")
    assert "derived" not in build_questions([base, derived], "value")[0]
    for fields in ([derived, base], [derived], [derived.model_copy(update={"source_field": "derived"})]):
        with pytest.raises(FieldError, match="earlier entity"):
            build_questions(fields, "value")
    choice = FieldDef(id="raw", kind="choice", instructions="q", criteria={"Yes": "Yes", "No": "No"})
    with pytest.raises(FieldError, match="earlier entity"):
        build_questions([choice, derived], "value")


def test_speaker_lines_preserve_roles_without_assuming_numbers():
    text = "Speaker 2: Hello from Bharosa.\nSpeaker 1: Hello.\nSpeaker 1: Please continue."
    for transcript in (text, {"text": text}):
        state, warnings = normalize_transcript(transcript)
        assert [t["speaker"] for t in state["turns"]] == ["spk2", "spk1"]
        assert state["turns"][1]["text"] == "Hello. Please continue."
        assert warnings
    with pytest.raises(ValueError, match="per line"):
        normalize_transcript({"text": "Speaker 2: Hello.\nUnlabelled response"})
    with pytest.raises(ValueError, match="per line"):
        normalize_transcript("Unlabelled response")


def test_blank_option_mapping_avoids_collisions_and_round_trips_probabilities():
    criteria = {"Yes": "Yes", "not_mentioned": "A literal option", "not_mentioned_2": "Another",
                "": "Not discussed", " ": "Unclear"}
    names = choice_option_names(criteria)
    assert names[""] == "not_mentioned_3"
    assert names[" "] == "not_mentioned_4"
    assert len(set(names.values())) == len(criteria)
    field = FieldDef(id="consent", kind="choice", instructions="Was consent obtained?",
                     criteria=criteria, output_path=["Loan_options", "CIBIL_Consent"])
    questions, _ = build_questions([field], "")
    assert set(questions["consent"]["criteria"]) == set(names.values())
    results, flags = build_results([field], {"consent": {
        "choice": names[""], "probabilities": {names[""]: 0.98, "Yes": 0.02},
    }}, {})
    assert flags == []
    assert results[0].value == ""
    assert results[0].probabilities == {"": 0.98, "Yes": 0.02}
    assert build_structured_output([field], results) == {"Loan_options": {"CIBIL_Consent": ""}}


@pytest.mark.parametrize("provider", ["jev", "microsoft"])
@respx.mock
def test_bharosa_never_sends_empty_option_names_to_either_provider(provider):
    s = scenario()
    fields = [f for f in s["fields"] if f["id"] in {
        "cibil_consent", "current_residence_type", "permanent_residence_type", "loan_rate_type",
    }]
    url = URL if provider == "microsoft" else "https://api.typesafe.ai/v1/systemone"

    def reject_empty_options(request):
        body = json.loads(request.content)
        for question in body["questions"].values():
            assert question["type"] == "choice"
            assert all(key.strip() for key in question["criteria"])
            assert "not_mentioned" in question["criteria"]
        return httpx.Response(200, json={"answers": {
            fid: {"choice": "not_mentioned", "confidence": 0.99} for fid in body["questions"]
        }})

    respx.post(url).mock(side_effect=reject_empty_options)
    response = client.post("/api/analyze", json={
        "api_key": "test-key", "provider": provider,
        "endpoint": "https://res.services.ai.azure.com" if provider == "microsoft" else None,
        "model": "Decision-1" if provider == "microsoft" else "jev-latest",
        "transcript": {"turns": [{"speaker": "customer", "text": "Just saying hello."}]},
        "fields": fields,
    })
    assert response.status_code == 200, response.text
    assert response.json()["structured_output"] == {
        "Current_Location": {"ResidenceType": ""},
        "Permanent_Location": {"ResidenceType": ""},
        "Loan": {"Rate_type": ""},
        "Loan_options": {"CIBIL_Consent": ""},
    }

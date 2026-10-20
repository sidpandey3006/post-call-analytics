import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from entities import MAX_CANDIDATES, NONE
from generator import build_chat_body, build_sample_body, parse_generated, parse_sample, suggest_templates
from providers import DecisionError, call_azure_chat, call_jev, call_microsoft
from models import AnalyzeRequest, AnalyzeResponse
from normalize import normalize_transcript, transcript_text
from postprocess import build_results, build_structured_output
from questions import FieldError, build_questions

app = FastAPI(title="Post-call analytics")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get(
        "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMPLATES = Path(__file__).parent / "templates"


class PreviewRequest(BaseModel):
    transcript: Any
    context: dict[str, Any] | None = None


@app.get("/api/health")
def health():
    return {"ok": True}


TEMPLATE_FILES = {"loan": "loan.json", "sales": "sales.json"}


@app.get("/api/scenarios")
def list_scenarios():
    scenarios = json.loads((TEMPLATES / "scenarios.json").read_text(encoding="utf-8"))
    scenarios.append(json.loads((TEMPLATES / "loan_extraction.json").read_text(encoding="utf-8")))
    return scenarios


@app.get("/api/templates/{name}")
def get_template(name: str):
    if name not in TEMPLATE_FILES:
        raise HTTPException(404, f"Unknown template '{name}'")
    return json.loads((TEMPLATES / TEMPLATE_FILES[name]).read_text(encoding="utf-8"))


@app.post("/api/normalize-preview")
def normalize_preview(req: PreviewRequest):
    try:
        state, warnings = normalize_transcript(req.transcript, req.context)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"state": state, "warnings": warnings, "turns": len(state["turns"]),
            "approx_tokens": len(json.dumps(state)) // 4}


class GenerateRequest(BaseModel):
    description: str = Field(min_length=20, max_length=2000)
    endpoint: str | None = None
    api_key: str | None = None
    chat_deployment: str | None = None
    max_fields: int = Field(default=10, ge=3, le=15)


@app.post("/api/generate-fields")
async def generate_fields(req: GenerateRequest):
    """With a Foundry chat deployment: generate fields. Otherwise: suggest curated templates."""
    if not (req.endpoint and req.api_key and req.chat_deployment):
        return {"mode": "suggestions", "matches": suggest_templates(req.description)}
    try:
        try:
            raw = await call_azure_chat(req.api_key, req.endpoint, req.chat_deployment,
                                        build_chat_body(req.description, req.max_fields))
        except DecisionError as e:
            # only fall back when the deployment doesn't support structured outputs
            if e.status == 400 and ("json_schema" in e.message or "response_format" in e.message):
                raw = await call_azure_chat(req.api_key, req.endpoint, req.chat_deployment,
                                            build_chat_body(req.description, req.max_fields, strict=False))
            else:
                raise
        content = raw["choices"][0]["message"]["content"]
        fields, rejected, warnings = parse_generated(content, req.max_fields)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (KeyError, IndexError, TypeError):
        raise HTTPException(502, "Unexpected response from the chat deployment")
    except DecisionError as e:
        msg = e.message.replace("model field must be your Foundry deployment name (Foundry portal > Deployments), not the model name.",
                                "chat deployment name must match a chat model deployment (e.g. gpt-4o) in your resource.")
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, msg)
    if not fields:
        raise HTTPException(422, f"No valid fields were generated. Rejected: {rejected}")
    sample = parse_sample(content)
    if sample is None:
        try:
            raw2 = await call_azure_chat(req.api_key, req.endpoint, req.chat_deployment,
                                         build_sample_body(req.description, fields))
            sample = parse_sample(raw2["choices"][0]["message"]["content"])
        except (DecisionError, KeyError, IndexError, TypeError):
            sample = None
    if sample is None:
        warnings.append("No sample transcript could be generated; paste your own transcript in section 1.")
    return {"mode": "generated", "fields": [f.model_dump() for f in fields], "rejected": rejected,
            "warnings": warnings, "sample": sample, "usage": raw.get("usage")}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    try:
        state, warnings = normalize_transcript(req.transcript, req.context)
        questions, candidates = build_questions(req.fields, transcript_text(state))
    except (ValueError, FieldError) as e:
        raise HTTPException(400, str(e))
    if not questions:
        raise HTTPException(400, "No questions to ask (entity fields found no candidates and no other fields defined)")
    limited = [fid for fid, values in candidates.items() if len(values) == MAX_CANDIDATES]
    if limited:
        warnings.append(f"Candidate limit ({MAX_CANDIDATES}) reached for {', '.join(limited)}. "
                        "Values later in the transcript may be missing; inspect the candidates or narrow the field regex.")
    body = {"state": state, "model": req.model, "questions": questions}
    try:
        if req.provider == "microsoft":
            if not req.endpoint:
                raise HTTPException(400, "Microsoft provider needs the Foundry resource endpoint")
            if not req.model.strip() or req.model == "jev-latest":
                raise HTTPException(400, "Microsoft provider needs your Foundry deployment name as the model")
            raw = await call_microsoft(req.api_key, body, req.endpoint, req.auth)
        else:
            raw = await call_jev(req.api_key, body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except DecisionError as e:
        raise HTTPException(e.status if 400 <= e.status < 600 else 502, e.message)
    results, flags = build_results(req.fields, raw.get("answers", {}), candidates)
    try:
        structured_output = build_structured_output(req.fields, results)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return AnalyzeResponse(results=results, flags=flags, state=state, warnings=warnings,
                           raw_request=body, raw_response=raw, usage=raw.get("usage"),
                           structured_output=structured_output)

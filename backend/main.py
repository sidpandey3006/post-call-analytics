import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from entities import NONE
from providers import DecisionError, call_jev, call_microsoft
from models import AnalyzeRequest, AnalyzeResponse
from normalize import normalize_transcript, transcript_text
from postprocess import build_results
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


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    try:
        state, warnings = normalize_transcript(req.transcript, req.context)
        questions, candidates = build_questions(req.fields, transcript_text(state))
    except (ValueError, FieldError) as e:
        raise HTTPException(400, str(e))
    if not questions:
        raise HTTPException(400, "No questions to ask (entity fields found no candidates and no other fields defined)")
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
    return AnalyzeResponse(results=results, flags=flags, state=state, warnings=warnings,
                           raw_request=body, raw_response=raw, usage=raw.get("usage"))

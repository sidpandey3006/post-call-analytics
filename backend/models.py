from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

FieldKind = Literal["noul", "choice", "score", "entity"]
EntityType = Literal["email", "phone", "amount", "date"]


class FieldDef(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    kind: FieldKind
    instructions: str = Field(min_length=1)
    # noul: {"true": "...", "false": "..."}; choice: {option: description}
    criteria: dict[str, str | None] | None = None
    # score: ordered level descriptions
    levels: list[str] | None = None
    entity_type: EntityType | None = None
    # Noul probabilities within [low, high] are flagged; choice/score/entity flag if confidence < min_confidence
    min_confidence: float = 0.7
    uncertain_band: tuple[float, float] = (0.3, 0.7)

    @field_validator("min_confidence")
    @classmethod
    def _conf(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("min_confidence must be within [0, 1]")
        return v


class AnalyzeRequest(BaseModel):
    api_key: str = Field(min_length=1)
    transcript: Any
    fields: list[FieldDef] = Field(min_length=1)
    context: dict[str, Any] | None = None
    model: str = "jev-latest"
    base_url: str = "https://api.typesafe.ai"


class FieldResult(BaseModel):
    id: str
    kind: FieldKind
    value: Any = None
    probability: float | None = None
    confidence: float | None = None
    probabilities: Any = None
    legend: Any = None
    entity_candidates: list[str] | None = None
    normalized: Any = None
    needs_review: bool = False
    review_reason: str | None = None


class AnalyzeResponse(BaseModel):
    results: list[FieldResult]
    flags: list[str]
    state: Any
    warnings: list[str]
    raw_request: Any
    raw_response: Any
    usage: dict[str, Any] | None = None

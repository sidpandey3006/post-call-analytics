"""Translate FieldDefs into Jev question objects."""
from entities import NONE, PatternError, find_candidates
from models import FieldDef

MAX_CHOICES = 255


class FieldError(ValueError):
    pass


def build_questions(fields: list[FieldDef], text: str) -> tuple[dict, dict[str, list[str]]]:
    """Return (questions, candidates_by_field_id)."""
    questions: dict = {}
    candidates: dict[str, list[str]] = {}
    seen: set[str] = set()
    paths: list[list[str]] = []
    for f in fields:
        if f.id in seen:
            raise FieldError(f"Duplicate field id: {f.id}")
        seen.add(f.id)
        if f.output_path is not None:
            if any(not key.strip() for key in f.output_path):
                raise FieldError(f"Field '{f.id}' has an empty output key")
            if any(p[:len(f.output_path)] == f.output_path or f.output_path[:len(p)] == p for p in paths):
                raise FieldError(f"Field '{f.id}' has a duplicate or conflicting output path")
            paths.append(f.output_path)
        if f.kind == "noul":
            q: dict = {"type": "noul", "instructions": f.instructions}
            if f.criteria:
                q["criteria"] = {k: v for k, v in f.criteria.items() if k in ("true", "false") and v}
                if not q["criteria"]:
                    del q["criteria"]
        elif f.kind == "choice":
            if not f.criteria or len(f.criteria) < 2:
                raise FieldError(f"Choice field '{f.id}' needs at least 2 options")
            if len(f.criteria) > MAX_CHOICES:
                raise FieldError(f"Choice field '{f.id}' exceeds {MAX_CHOICES} options")
            q = {"type": "choice", "instructions": f.instructions, "criteria": dict(f.criteria)}
        elif f.kind == "score":
            if not f.levels or len(f.levels) < 2:
                raise FieldError(f"Score field '{f.id}' needs at least 2 levels")
            q = {"type": "score", "instructions": f.instructions, "criteria": list(f.levels)}
        elif f.kind == "entity":
            if not f.entity_type:
                raise FieldError(f"Entity field '{f.id}' needs entity_type")
            try:
                cands = find_candidates(f.entity_type, text, f.pattern)
            except PatternError as e:
                raise FieldError(f"Field '{f.id}': {e}")
            candidates[f.id] = cands
            if not cands:
                continue  # nothing to pick from; reported as not found
            if len(cands) > MAX_CHOICES - 1:
                cands = cands[: MAX_CHOICES - 1]
                candidates[f.id] = cands
            crit: dict = {c: None for c in cands}
            crit[NONE] = "None of these is the requested value."
            q = {"type": "choice", "instructions": f.instructions, "criteria": crit}
        else:
            raise FieldError(f"Unknown kind {f.kind}")
        questions[f.id] = q
    return questions, candidates

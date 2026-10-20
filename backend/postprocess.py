from datetime import datetime
from decimal import Decimal, InvalidOperation

from entities import NONE, normalize_entity
from models import FieldDef, FieldResult


def _confidence(a: dict) -> float | None:
    """Use the provider's confidence when present, else the top option probability."""
    c = a.get("confidence")
    if isinstance(c, (int, float)):
        return c
    p = a.get("probabilities")
    if isinstance(p, dict):
        vals = [v for v in p.values() if isinstance(v, (int, float))]
        return max(vals) if vals else None
    if isinstance(p, list):
        vals = [v for v in p if isinstance(v, (int, float))]
        return max(vals) if vals else None
    return None


def build_results(fields: list[FieldDef], answers: dict, candidates: dict[str, list[str]],
                  reference: datetime | None = None) -> tuple[list[FieldResult], list[str]]:
    results: list[FieldResult] = []
    flags: list[str] = []
    for f in fields:
        r = FieldResult(id=f.id, kind=f.kind)
        a = answers.get(f.id)
        if f.kind == "entity":
            r.entity_candidates = candidates.get(f.id, [])
            if a is None:
                r.needs_review = bool(r.entity_candidates)
                r.review_reason = "No answer returned" if r.entity_candidates else "No candidates found in transcript"
            else:
                r.value = a.get("choice")
                r.confidence = _confidence(a)
                r.probabilities = a.get("probabilities")
                if r.value == NONE:
                    r.value = None
                    r.review_reason = "Model found no matching candidate"
                elif r.value not in r.entity_candidates:
                    r.value = None
                    r.needs_review, r.review_reason = True, "Model returned a value outside transcript candidates"
                else:
                    r.normalized = normalize_entity(f.entity_type, r.value, reference)
                    if r.normalized is None:
                        r.needs_review, r.review_reason = True, "Could not normalize value"
                if r.value is not None and (r.confidence or 0) < f.min_confidence:
                    r.needs_review, r.review_reason = True, f"Low confidence ({r.confidence})"
        elif a is None:
            r.needs_review, r.review_reason = True, "No answer returned"
        elif f.kind == "noul":
            r.value = r.probability = a.get("noul", a.get("probability"))
            lo, hi = f.uncertain_band
            if r.probability is not None and lo <= r.probability <= hi:
                r.needs_review, r.review_reason = True, f"Uncertain probability ({r.probability:.2f})"
        else:
            r.value = a.get("choice") if f.kind == "choice" else a.get("score")
            r.confidence = _confidence(a)
            r.probabilities = a.get("probabilities")
            r.legend = a.get("legend")
            if r.confidence is not None and r.confidence < f.min_confidence:
                r.needs_review, r.review_reason = True, f"Low confidence ({r.confidence})"
        if r.needs_review:
            flags.append(f"{f.id}: {r.review_reason}")
        results.append(r)
    return results, flags


def build_structured_output(fields: list[FieldDef], results: list[FieldResult]) -> dict | None:
    output: dict = {}
    by_id = {r.id: r for r in results}
    for f in fields:
        if not f.output_path:
            continue
        r = by_id[f.id]
        value = r.value if r.value is not None else ""
        if f.output_type == "number" and value != "":
            source = r.normalized.get("amount") if isinstance(r.normalized, dict) else value
            try:
                number = Decimal(str(source).replace(",", ""))
                if not number.is_finite():
                    raise InvalidOperation
                value = int(number) if number == number.to_integral_value() else float(number)
            except (InvalidOperation, ValueError, OverflowError):
                raise ValueError(f"Field '{f.id}' cannot be exported as a number")
        target = output
        for key in f.output_path[:-1]:
            target = target.setdefault(key, {})
        target[f.output_path[-1]] = value
    return output or None

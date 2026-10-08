from datetime import datetime

from entities import NONE, normalize_entity
from models import FieldDef, FieldResult


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
                r.needs_review = False
                r.review_reason = "No candidates found in transcript"
            else:
                r.value = a.get("choice")
                r.confidence = a.get("confidence")
                r.probabilities = a.get("probabilities")
                if r.value == NONE:
                    r.value = None
                    r.review_reason = "Model found no matching candidate"
                else:
                    r.normalized = normalize_entity(f.entity_type, r.value, reference)
                    if r.normalized is None:
                        r.needs_review, r.review_reason = True, "Could not normalize value"
                if r.value is not None and (r.confidence or 0) < f.min_confidence:
                    r.needs_review, r.review_reason = True, f"Low confidence ({r.confidence})"
        elif a is None:
            r.needs_review, r.review_reason = True, "No answer returned"
        elif f.kind == "noul":
            r.value = r.probability = a.get("noul")
            lo, hi = f.uncertain_band
            if r.probability is not None and lo <= r.probability <= hi:
                r.needs_review, r.review_reason = True, f"Uncertain probability ({r.probability:.2f})"
        else:
            r.value = a.get("choice") if f.kind == "choice" else a.get("score")
            r.confidence = a.get("confidence")
            r.probabilities = a.get("probabilities")
            r.legend = a.get("legend")
            if r.confidence is not None and r.confidence < f.min_confidence:
                r.needs_review, r.review_reason = True, f"Low confidence ({r.confidence})"
        if r.needs_review:
            flags.append(f"{f.id}: {r.review_reason}")
        results.append(r)
    return results, flags

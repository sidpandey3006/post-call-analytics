"""Normalize vendor STT JSON into a compact, evidence-friendly state."""
import re
from typing import Any

SPEAKER_ALIASES = {
    "agent": "agent", "rep": "agent", "sales_rep": "agent", "assistant": "agent", "bot": "agent",
    "customer": "customer", "caller": "customer", "client": "customer", "user": "customer",
    "lead": "customer", "prospect": "customer",
}


def _speaker(raw: Any) -> str:
    if raw is None:
        return "unknown"
    s = str(raw).strip().lower().replace(" ", "_")
    if s in SPEAKER_ALIASES:
        return SPEAKER_ALIASES[s]
    # Numeric / labelled channels (0, 1, "speaker_0", "A", "B") are kept as-is
    return s.replace("speaker_", "spk") if s.startswith("speaker_") else (f"spk{s}" if s.isdigit() else s)


def _num(*vals: Any) -> float | None:
    for v in vals:
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _ms_or_s(value: float | None, ms: bool) -> float | None:
    if value is None:
        return None
    return round(value / 1000, 2) if ms else round(value, 2)


def _extract_segments(data: Any) -> tuple[list[dict], dict]:
    """Return raw segments [{speaker,text,start,end}] and extra metadata."""
    meta: dict = {}
    if isinstance(data, list):
        return _segments_from_list(data), meta
    if not isinstance(data, dict):
        raise ValueError("Transcript must be a JSON object or array")

    for key in ("call_id", "agent_id", "duration", "language", "direction"):
        if key in data:
            meta[key] = data[key]

    # Azure fast transcription uses millisecond offsets and text directly on each phrase.
    if isinstance(data.get("phrases"), list) and data["phrases"]:
        segs = []
        for p in data["phrases"]:
            if not isinstance(p, dict):
                continue
            start = _ms_or_s(_num(p.get("offsetMilliseconds")), True)
            duration = _ms_or_s(_num(p.get("durationMilliseconds")), True)
            segs.append({"speaker": p.get("speaker"), "text": p.get("text", ""),
                         "start": start,
                         "end": round(start + duration, 2) if start is not None and duration is not None else None})
        duration = _ms_or_s(_num(data.get("durationMilliseconds")), True)
        if duration is not None:
            meta.setdefault("duration", duration)
        locales = {p["locale"] for p in data["phrases"] if isinstance(p, dict) and isinstance(p.get("locale"), str)}
        if len(locales) == 1:
            meta.setdefault("language", locales.pop())
        return segs, meta
    if isinstance(data.get("combinedPhrases"), list):
        return _segments_from_list(data["combinedPhrases"]), meta
    # AssemblyAI: utterances with ms timestamps
    if isinstance(data.get("utterances"), list):
        return _segments_from_list(data["utterances"], ms=True), meta
    # Generic / simple formats
    for key in ("turns", "segments", "transcript", "messages", "conversation"):
        if isinstance(data.get(key), list):
            return _segments_from_list(data[key]), meta
    # Deepgram: results.channels[].alternatives[].paragraphs / utterances
    results = data.get("results")
    if isinstance(results, dict):
        if isinstance(results.get("utterances"), list):
            return _segments_from_list(results["utterances"]), meta
        segs = []
        for ci, ch in enumerate(results.get("channels", [])):
            alts = ch.get("alternatives") or [{}]
            paras = (alts[0].get("paragraphs") or {}).get("paragraphs")
            if paras:
                for p in paras:
                    text = " ".join(s.get("text", "") for s in p.get("sentences", []))
                    segs.append({"speaker": p.get("speaker", ci), "text": text,
                                 "start": p.get("start"), "end": p.get("end")})
            elif alts[0].get("transcript"):
                segs.append({"speaker": ci, "text": alts[0]["transcript"], "start": None, "end": None})
        if segs:
            return segs, meta
    # Azure batch: recognizedPhrases
    if isinstance(data.get("recognizedPhrases"), list):
        segs = []
        for p in data["recognizedPhrases"]:
            best = (p.get("nBest") or [{}])[0]
            segs.append({"speaker": p.get("speaker", p.get("channel")), "text": best.get("display", ""),
                         "start": _num(p.get("offsetInTicks") and p["offsetInTicks"] / 1e7),
                         "end": None})
        return segs, meta
    # Whisper-style: plain text only
    if isinstance(data.get("text"), str):
        return [{"speaker": None, "text": data["text"], "start": None, "end": None}], meta
    raise ValueError("Unrecognized transcript format: expected turns/segments/utterances/results/phrases/combinedPhrases/recognizedPhrases/text")


def _segments_from_list(items: list, ms: bool = False) -> list[dict]:
    segs = []
    for it in items:
        if isinstance(it, str):
            segs.append({"speaker": None, "text": it, "start": None, "end": None})
            continue
        if not isinstance(it, dict):
            continue
        text = it.get("text") or it.get("transcript") or it.get("content") or it.get("message") or ""
        speaker = next((it[k] for k in ("speaker", "role", "speaker_label", "channel", "participant") if k in it), None)
        start = _num(it.get("start"), it.get("start_time"), it.get("startTime"), it.get("ts"))
        end = _num(it.get("end"), it.get("end_time"), it.get("endTime"))
        segs.append({"speaker": speaker, "text": str(text), "start": _ms_or_s(start, ms), "end": _ms_or_s(end, ms)})
    return segs


def normalize_transcript(data: Any, context: dict | None = None) -> tuple[dict, list[str]]:
    """Return (state, warnings). Consecutive same-speaker segments are merged."""
    warnings: list[str] = []
    segs, meta = _extract_segments(data)
    turns: list[dict] = []
    for s in segs:
        text = " ".join(s["text"].split())
        if not text:
            continue
        spk = _speaker(s["speaker"])
        if turns and turns[-1]["speaker"] == spk:
            turns[-1]["text"] += " " + text
            if s["end"] is not None:
                turns[-1]["end"] = s["end"]
            continue
        turns.append({"speaker": spk, "start": s["start"], "end": s["end"], "text": text})
    if not turns:
        raise ValueError("Transcript contains no text")
    for i, t in enumerate(turns, 1):
        t["i"] = i
        if t["end"] is None:
            del t["end"]
        if t["start"] is None:
            del t["start"]
    speakers = {t["speaker"] for t in turns}
    named = {s for s in speakers if s != "unknown" and not re.fullmatch(r"spk\w*|[a-z]|channel_?\d+", s)}
    if not named:
        warnings.append("Speaker roles are not labelled agent/customer; role-based questions may be unreliable.")
    state: dict = {**meta, "turns": [{"i": t["i"], **{k: v for k, v in t.items() if k != "i"}} for t in turns]}
    if context:
        state["context"] = context
    approx_tokens = len(str(state)) // 4
    if approx_tokens > 60000:
        warnings.append(f"State is ~{approx_tokens} tokens; Jev's context is ~64k. Consider trimming.")
    return state, warnings


def transcript_text(state: dict) -> str:
    """Plain text of all turns, used for entity candidate discovery."""
    return "\n".join(t["text"] for t in state["turns"])

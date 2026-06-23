"""
agents/core.py — the single LLM egress point for the LOFI agent.

COMPLIANCE GUARD (Verwerkersovereenkomst art. 3.5 / 3.7)
--------------------------------------------------------
Real inference only runs when LOFI_LLM_ENABLED is truthy. Until then the wrapper
runs in MOCK mode and makes **no network calls** — so the UI is fully
visualisable without sending any data to an external LLM.

Path C was chosen: the direct Anthropic API (US inference) under Anthropic's DPA
+ EU SCCs + zero-data-retention. The direct API cannot keep data in the EEA
(inference_geo only offers "us"/"global"; workspace geo is "us"-only), so
LOFI_LLM_ENABLED must ONLY be set once Lofi's *amended* written permission for
US-hosting-under-SCCs and account-level zero-retention are both confirmed.

Everything Claude ever sees passes through `to_model_view()` (data minimisation).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

MODEL = os.environ.get("LOFI_LLM_MODEL", "claude-opus-4-8")
# "us" = deterministic US (1.1x), cleaner to document for SCCs than "global".
INFERENCE_GEO = os.environ.get("LOFI_LLM_INFERENCE_GEO", "us")
MAX_TOKENS = 8000


# ── mode / compliance ────────────────────────────────────────────────────────

def _enabled_flag() -> bool:
    return os.environ.get("LOFI_LLM_ENABLED", "").strip().lower() in (
        "1", "true", "yes", "on")


def _anthropic_ready() -> tuple[bool, str]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False, "ANTHROPIC_API_KEY niet ingesteld"
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False, "anthropic SDK niet geïnstalleerd"
    return True, ""


def is_live() -> bool:
    return _enabled_flag() and _anthropic_ready()[0]


def compliance_status() -> dict:
    """Audit surface the UI can display so the active mode is always visible."""
    if not _enabled_flag():
        reason = "LOFI_LLM_ENABLED staat uit (voorbeeldmodus)"
        mode = "mock"
    else:
        ok, why = _anthropic_ready()
        mode, reason = ("live", "Claude actief") if ok else ("mock", why)
    return {"mode": mode, "model": MODEL, "inference_geo": INFERENCE_GEO,
            "reason": reason}


def _client():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def _create(**kwargs):
    """Central Claude call. Injects inference_geo robustly across SDK versions."""
    client = _client()
    kwargs.setdefault("model", MODEL)
    try:
        return client.messages.create(inference_geo=INFERENCE_GEO, **kwargs)
    except TypeError:
        # older SDK without a typed inference_geo kwarg
        extra = kwargs.pop("extra_body", {}) or {}
        extra["inference_geo"] = INFERENCE_GEO
        return client.messages.create(extra_body=extra, **kwargs)


# ── data minimisation (the only thing Claude ever sees) ──────────────────────

def to_model_view(c: dict, *, booking_history: list[dict] | None = None) -> dict:
    """Strip a candidate down to the allow-listed fields. `booking_history`
    (gages/past bookings) is Phase 3 and only included when Lofi approved it."""
    view = {
        "artist_id": c.get("artist_id"),
        "name": c.get("artist_name"),
        "genres": (c.get("genres") or [])[:6],
        "career_status": c.get("career_status"),
        "spotify_listeners": c.get("spotify_listeners"),
        "scores": {
            "momentum": c.get("momentum"),
            "growth": c.get("growth"),
            "market_relevance": c.get("market_relevance"),
            "future_potential": c.get("future_potential"),
            "confidence": c.get("confidence"),
        },
        "forecast_90d": c.get("forecast_90d"),
    }
    if booking_history:
        view["booking_history"] = booking_history  # Phase 3, gage-approved
    return view


# ── prompts ──────────────────────────────────────────────────────────────────

def _taxonomy_block() -> str:
    from scout.ranking import load_taxonomy
    t = load_taxonomy()
    g = t.get("genres", {})
    b = t.get("benchmark_artists", {})
    return (
        "Kerngenres: " + ", ".join(g.get("tier_1", [])) + ". "
        "Aanverwant: " + ", ".join(g.get("tier_2", [])) + ". "
        "Referentie-artiesten: "
        + ", ".join(b.get("tier_a_plus", []) + b.get("tier_a", [])) + "."
    )


_SCOUT_SYSTEM = (
    "Je bent de scout van LOFI, een boekingsbureau voor tech-house en house DJ's. "
    "Je schrijft voor een niet-technisch boekingsteam, in helder Nederlands. "
    "Onderbouw elke keuze met concrete signalen uit de data (groei, momentum, "
    "forecast, genre-fit). Verzin niets en gebruik alleen de aangeleverde gegevens.\n"
)


def _chat_system(artist_view: dict) -> str:
    has_bookings = bool(artist_view.get("booking_history")
                        or artist_view.get("comparables"))
    lines = [
        "Je bent de artiest-adviseur van LOFI, een boekingsbureau voor tech-house "
        "en house. Je helpt het (niet-technische) boekingsteam beslissen over "
        "ÉÉN artiest, in helder en bondig Nederlands.",
        "",
        "Waar je mee helpt:",
        "- Een onderbouwd boekingsoordeel (ja / nee / twijfel) op basis van "
        "genre-fit, groei, momentum, potentieel, forecast en datadekking.",
        "- Uitleggen waarom een artiest groeit of juist afvlakt, in gewone taal.",
        "- Vergelijken met de referentie-artiesten en met eerdere LOFI-boekingen.",
        "- Een realistische gage-indicatie geven op basis van vergelijkbare "
        "eerdere boekingen — alleen als die boekingsdata is meegegeven.",
        "- Risico's benoemen (dalende forecast, weinig data, genre buiten profiel).",
        "- Een korte interne notitie of pitch schrijven.",
        "",
        "Regels:",
        "- Gebruik UITSLUITEND de aangeleverde gegevens; verzin geen cijfers, "
        "gages of boekingen.",
        "- Noem kort waar een claim op rust (welke score, metric of boeking).",
        "- Wees eerlijk over onzekerheid en ontbrekende data.",
        "- Een hoge groei-score met een negatieve forecast is een tegenstrijdig "
        "signaal — benoem dat in plaats van het te negeren.",
    ]
    if not has_bookings:
        lines.append(
            "- LET OP: er is nog GEEN LOFI-boekingsdata (Airtable) gekoppeld. "
            "Geef dus geen gage-bedragen of uitspraken over eerdere boekingen; "
            "zeg dat die data nog niet beschikbaar is.")
    lines += ["", _taxonomy_block(),
              "", "Gegevens van deze artiest (JSON):",
              json.dumps(artist_view, ensure_ascii=False)]
    return "\n".join(lines)


# ── Scout rationales (structured output) ─────────────────────────────────────

_RATIONALE_SCHEMA = {
    "type": "object",
    "properties": {
        "rationales": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "artist_id": {"type": "string"},
                    "rationale_nl": {"type": "string"},
                    "fit_score": {"type": "integer"},
                },
                "required": ["artist_id", "rationale_nl", "fit_score"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["rationales"],
    "additionalProperties": False,
}


def generate_rationales(candidates: list[dict]) -> dict[str, dict]:
    """artist_id -> {"rationale_nl", "fit_score"}.

    MOCK mode reuses the deterministic `waarom`/`rank` so the UI is visualisable;
    LIVE mode asks Claude for a one-line Dutch rationale + fit per artist.
    """
    if not is_live():
        return {
            c["artist_id"]: {
                "rationale_nl": c.get("waarom", ""),
                "fit_score": round(c.get("rank", 0)),
            }
            for c in candidates
        }

    views = [to_model_view(c) for c in candidates]
    user = (
        "Geef voor elke artiest één korte Nederlandse toelichting (één zin) voor "
        "de boeking-shortlist, plus een fit_score 0-100. Kandidaten (JSON):\n"
        + json.dumps(views, ensure_ascii=False)
    )
    resp = _create(
        max_tokens=MAX_TOKENS,
        system=_SCOUT_SYSTEM,
        output_config={"format": {"type": "json_schema",
                                  "schema": _RATIONALE_SCHEMA}},
        messages=[{"role": "user", "content": user}],
    )
    if getattr(resp, "stop_reason", None) == "refusal":
        raise RuntimeError(f"Claude weigerde het verzoek: {resp.stop_details}")
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    data = json.loads(text)
    return {
        r["artist_id"]: {"rationale_nl": r["rationale_nl"],
                         "fit_score": r["fit_score"]}
        for r in data.get("rationales", [])
    }


# ── Per-artist chat (streaming) ──────────────────────────────────────────────

def chat_stream(artist_view: dict, history: list[dict], user_msg: str):
    """Yields text chunks. MOCK mode yields a clearly-labelled placeholder."""
    if not is_live():
        yield ("[Voorbeeldmodus] De AI-assistent staat nog uit. Zodra Claude is "
               "ingeschakeld beantwoord ik hier je vraag over "
               f"{artist_view.get('name', 'deze artiest')}.")
        return

    client = _client()
    messages = list(history) + [{"role": "user", "content": user_msg}]
    kw = dict(model=MODEL, max_tokens=4000,
              system=_chat_system(artist_view), messages=messages)
    try:
        stream_cm = client.messages.stream(inference_geo=INFERENCE_GEO, **kw)
    except TypeError:
        stream_cm = client.messages.stream(
            extra_body={"inference_geo": INFERENCE_GEO}, **kw)
    with stream_cm as stream:
        for text in stream.text_stream:
            yield text


# ── CLI self-test (a safe way to verify your token + where inference runs) ───

def _selftest() -> int:
    st = compliance_status()
    print(f"Mode: {st['mode']}  |  model: {st['model']}  |  "
          f"inference_geo: {st['inference_geo']}  |  {st['reason']}")
    sample = [{
        "artist_id": "demo", "artist_name": "Demo DJ", "genres": ["tech house"],
        "career_status": "mid", "spotify_listeners": 120000,
        "momentum": 78, "growth": 81, "market_relevance": 55,
        "future_potential": 84, "confidence": 90, "forecast_90d": 64.0,
        "waarom": "Sterke groeiversnelling, kerngenre (tech house).", "rank": 80,
    }]
    out = generate_rationales(sample)
    print("Rationale:", out.get("demo"))
    if is_live():
        print("Live call OK — check the Anthropic Console usage to confirm geo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())

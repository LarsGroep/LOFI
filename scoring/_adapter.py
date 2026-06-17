"""
_adapter.py — load any time-series origin into ONE canonical long form.

`load_long_series(spec)` is the only seam through which data enters the predictor.
Today it reads the tidy-long Chartmetric CSV your teammate produces. When more
artists arrive in that same format, nothing downstream changes. Supabase / live
Chartmetric origins are documented stubs that raise until those schemas exist —
they normalise into the identical row shape, so the rest of the pipeline is blind
to where the data came from.

Canonical row (one per observation):
    {
      "artist_id":             "cm_240495",
      "chartmetric_artist_id": 240495,
      "artist_name":           "Len Faki",
      "source":                "spotify",
      "metric":                "listeners",
      "d":                     "2025-06-09",     # normalised YYYY-MM-DD
      "val":                   93198.0,
      "carried":               True,             # interpolation / carry-forward
      "geo":                   None,             # {code2, location_name, is_estimate} for geo rows
      "endpoint_label":        "spotify_listeners",
      "pulled_at":             "2026-06-15T09:20:39...",
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from scoring._series import norm_date


@dataclass
class SourceSpec:
    kind: str                       # "csv" | "supabase" | "chartmetric"
    path: str | None = None         # for csv
    artist_ids: list[str] | None = None
    options: dict = field(default_factory=dict)


# ── Public entrypoint ─────────────────────────────────────────────────────────────

def load_long_series(spec: SourceSpec) -> list[dict]:
    if spec.kind == "csv":
        return _load_csv(spec.path)
    if spec.kind == "supabase":
        return _load_supabase(spec)
    if spec.kind == "snapshot":             # cached Supabase pull (offline, reproducible)
        return load_snapshot(spec.path)[0]
    if spec.kind == "chartmetric":
        return _load_chartmetric(spec)      # documented stub
    raise ValueError(f"unknown source kind: {spec.kind!r}")


def load_snapshot(path: str | None):
    """Read a cached pull (see scoring/pull_booked_timeseries.py) -> (rows, meta)."""
    if not path:
        raise ValueError("snapshot source requires a path")
    snap = json.loads(Path(path).read_text())
    return canonical_from_records(snap["artists"], pulled_at=snap.get("pulled_at", "snapshot"))


# ── CSV origin (the format we have today) ─────────────────────────────────────────

def _load_csv(path: str | None) -> list[dict]:
    if not path:
        raise ValueError("csv source requires a path")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)

    rows: list[dict] = []
    for r in df.to_dict("records"):
        try:
            val = float(r["value"])
        except (TypeError, ValueError):
            continue
        extra = _parse_json(r.get("extra_json"))
        geo = None
        if "location_name" in extra or extra.get("location_group"):
            geo = {
                "code2": extra.get("code2"),
                "location_name": extra.get("location_name"),
                "region": extra.get("region"),
                "is_estimate": bool(extra.get("is_estimate")),
            }
        rows.append({
            "artist_id": r.get("artist_id") or f"cm_{r.get('chartmetric_artist_id')}",
            "chartmetric_artist_id": _to_int(r.get("chartmetric_artist_id")),
            "artist_name": r.get("artist_name"),
            "source": r["source"],
            "metric": r["metric"],
            "d": norm_date(r["date"]),
            "val": val,
            # `carried` uses the explicit flag first, with a flat-run backstop so a
            # future endpoint that omits is_interpolated is still handled.
            "interp_flag": bool(extra.get("is_interpolated")),
            "diff": extra.get("diff"),
            "geo": geo,
            # geo metrics carry MANY rows per (source,metric,date) — one per country/
            # city — so location must be part of the identity or dedup collapses them.
            "loc": (geo or {}).get("location_name") or (geo or {}).get("code2") or "",
            "endpoint_label": r.get("endpoint_label"),
            "pulled_at": r.get("pulled_at"),
        })

    return _finalise(rows)


def _finalise(rows: list[dict]) -> list[dict]:
    """Dedup to one row per (artist,source,metric,date) keeping the latest pull, then
    derive the `carried` flag (explicit interpolation OR a flat run with diff 0/None)."""
    df = pd.DataFrame(rows)
    if df.empty:
        return []
    # Vintage check: as_of_slice enforces date-of-OBSERVATION (d<=t), but NOT
    # date-of-KNOWLEDGE. If the same (artist,source,metric,date) was pulled at multiple
    # times with different values (Chartmetric revising estimates), keeping the latest
    # could leak a future revision into a past-origin backtest. Dormant on a single
    # one-shot pull; warn loudly the moment accumulating multi-pull histories appear so
    # we add a pulled_at<=knowledge_cutoff filter before trusting backtests.
    vint = df.groupby(["artist_id", "source", "metric", "d", "loc"])["pulled_at"].nunique()
    revised = int((vint > 1).sum())
    if revised:
        print(f"[adapter] WARNING: {revised} (artist,source,metric,date) keys have >1 "
              f"pulled_at vintage. Keeping latest. Point-in-time BACKTESTS are only "
              f"leakage-free on a single-vintage snapshot until pulled_at vintage "
              f"filtering lands (see docs/decisions.md).")
    df = (df.sort_values("pulled_at")
            .drop_duplicates(["artist_id", "source", "metric", "d", "loc"], keep="last")
            .sort_values(["artist_id", "source", "metric", "loc", "d"]))

    out: list[dict] = []
    for _, g in df.groupby(["artist_id", "source", "metric", "loc"], sort=False):
        prev_val = None
        for rec in g.to_dict("records"):
            flat = (prev_val is not None and rec["val"] == prev_val
                    and rec.get("diff") in (0, "0", None, ""))
            rec["carried"] = bool(rec.get("interp_flag")) or flat
            prev_val = rec["val"]
            out.append({k: rec[k] for k in (
                "artist_id", "chartmetric_artist_id", "artist_name", "source",
                "metric", "d", "val", "carried", "geo", "endpoint_label", "pulled_at")})
    return out


# ── Documented stubs for future origins (identical output shape) ──────────────────

def _load_supabase(spec: SourceSpec) -> list[dict]:
    """Live origin: tinder.artists ⋈ artist_chartmetric.cm_timeseries.

    cm_timeseries is the nested Chartmetric shape {source: {metric: [{date,value}]}}
    (e.g. {"spotify": {"listeners": [...], "followers": [...]}, "cpp": {"rank": [...],
    "score": [...]}, "instagram": {...}}). No interpolation flag in the jsonb, so
    `carried` is derived from the flat-run backstop in _finalise. cpp.* is remapped to
    source 'chartmetric' to match metrics_vocab. Identity comes from chartmetric_id.

    options: {candidate_status: "booked"|None, schema: "tinder"}. Creds from env
    SUPABASE_URL + SUPABASE_KEY (or SUPABASE_ANON_KEY).
    """
    records = fetch_artist_records(
        candidate_status=(spec.options or {}).get("candidate_status"),
        schema=(spec.options or {}).get("schema", "tinder"),
        artist_ids=spec.artist_ids,
    )
    rows, _meta = canonical_from_records(records, pulled_at="supabase")
    return rows


def _load_chartmetric(spec: SourceSpec) -> list[dict]:
    """Live pull. scrapers/chartmetric_client.get_full_timeseries() already returns
    {source:{metric:[{date,value}]}}; map it into canonical rows here. NOTE: do NOT
    import compute_growth_features / and do not anchor on date.today() — those leak.
    This adapter only reshapes; the predictor slices point-in-time downstream."""
    raise NotImplementedError(
        "chartmetric origin not wired yet — use kind='csv'. See docstring for the shape.")


# ── helpers ───────────────────────────────────────────────────────────────────────

def _parse_json(s) -> dict:
    if not s:
        return {}
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return {}


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def group_by_artist(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["artist_id"], []).append(r)
    return out


# ── Nested cm_timeseries → canonical rows (shared by live + snapshot paths) ────────

def _map_nested_metric(platform: str, metric: str) -> tuple[str, str]:
    """Map a (jsonb platform key, metric key) to canonical (source, metric).
    cpp.rank/score live under their own top-level key but belong to source 'chartmetric'
    so they match metrics_vocab (chartmetric.cpp_rank / chartmetric.cpp_score)."""
    if platform == "cpp":
        return "chartmetric", f"cpp_{metric}"
    return platform, metric


def rows_from_nested_timeseries(artist_id: str, cm_id, name: str, ts: dict,
                                pulled_at: str = "snapshot") -> list[dict]:
    """Explode one artist's nested cm_timeseries jsonb into pre-_finalise raw rows."""
    out: list[dict] = []
    for platform, metrics in (ts or {}).items():
        if not isinstance(metrics, dict):
            continue
        for metric, pts in metrics.items():
            if not isinstance(pts, list):
                continue
            source, metric_c = _map_nested_metric(platform, metric)
            for p in pts:
                if not isinstance(p, dict):
                    continue
                d, v = p.get("date"), p.get("value")
                if d is None or v is None:
                    continue
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                out.append({
                    "artist_id": artist_id,
                    "chartmetric_artist_id": _to_int(cm_id),
                    "artist_name": name,
                    "source": source,
                    "metric": metric_c,
                    "d": norm_date(d),
                    "val": v,
                    "interp_flag": False,    # jsonb has no flag -> flat-run backstop only
                    "diff": None,
                    "geo": None,
                    "loc": "",
                    "endpoint_label": f"{source}_{metric_c}",
                    "pulled_at": pulled_at,
                })
    return out


def canonical_from_records(records: list[dict], pulled_at: str = "snapshot"):
    """records: [{artist_id, chartmetric_artist_id, name, candidate_status, lofi_score,
    cm_timeseries}, ...] (the snapshot shape). Returns (canonical_rows, meta_by_artist)."""
    raw, meta = [], {}
    for a in records:
        aid = a["artist_id"]
        raw += rows_from_nested_timeseries(
            aid, a.get("chartmetric_artist_id"), a.get("name"),
            a.get("cm_timeseries"), pulled_at)
        meta[aid] = {k: a.get(k) for k in
                     ("name", "chartmetric_artist_id", "candidate_status", "lofi_score")}
    return _finalise(raw), meta


def fetch_artist_records(candidate_status: str | None = "booked", schema: str = "tinder",
                         artist_ids: list[str] | None = None, page: int = 200) -> list[dict]:
    """Page through tinder.artists ⋈ artist_chartmetric and return snapshot-shape records
    (one per artist that has a cm_timeseries). Used by the live loader and the pull CLI."""
    import os
    from supabase import create_client

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    if not (url and key):
        raise RuntimeError("set SUPABASE_URL and SUPABASE_KEY (or SUPABASE_ANON_KEY)")
    sb = create_client(url, key)

    out: list[dict] = []
    off = 0
    while True:
        q = (sb.schema(schema).table("artists")
             .select("id,name,chartmetric_id,candidate_status,lofi_feel,"
                     "artist_chartmetric(cm_timeseries)"))
        if candidate_status:
            q = q.eq("candidate_status", candidate_status)
        batch = q.range(off, off + page - 1).execute().data or []
        for a in batch:
            ac = a.get("artist_chartmetric")
            ac = ac[0] if isinstance(ac, list) and ac else ac
            ts = (ac or {}).get("cm_timeseries") if ac else None
            if not ts:
                continue
            cmid = a.get("chartmetric_id")
            out.append({
                "artist_id": f"cm_{cmid}" if cmid else a["id"],
                "chartmetric_artist_id": _to_int(cmid),
                "name": a.get("name"),
                "candidate_status": a.get("candidate_status"),
                "lofi_score": (a.get("lofi_feel") or {}).get("score"),
                "cm_timeseries": ts,
            })
        if len(batch) < page:
            break
        off += page
    if artist_ids:
        keep = set(artist_ids)
        out = [a for a in out if a["artist_id"] in keep]
    return out

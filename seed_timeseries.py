"""
Overnight Chartmetric time-series seed for all LOFI-booked artists.

Reads tinder.artist_cache WHERE lofi_booked = TRUE.
- Artists WITHOUT chartmetric_id: searches CM first (1 call), saves cm_id, then fetches timeseries.
- Artists WITH chartmetric_id: fetches timeseries directly.

Skips artists that already have cm_timeseries unless --force is passed.
Rate: 2.1s/call. Est. 8-10s per enriched artist, 20s per unenriched one.

Usage:
    python seed_timeseries.py [--force] [--days 180]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# ── Chartmetric client ────────────────────────────────────────────────────────

_BASE = "https://api.chartmetric.com/api"
_RATE = 2.1
_tok = ""
_tok_exp = 0.0


def _refresh():
    global _tok, _tok_exp
    rt = os.environ.get("CHARTMETRIC_REFRESH_TOKEN", "").strip()
    if not rt:
        print("ERROR: CHARTMETRIC_REFRESH_TOKEN not set in .env")
        sys.exit(1)
    r = httpx.post(f"{_BASE}/token", json={"refreshtoken": rt}, timeout=15)
    r.raise_for_status()
    d = r.json()
    _tok = d["token"]
    _tok_exp = time.time() + d.get("expires_in", 3600) - 60


def _get(path: str, params: dict | None = None) -> dict | None:
    global _tok, _tok_exp
    time.sleep(_RATE)
    if time.time() >= _tok_exp:
        _refresh()
    for attempt in range(3):
        try:
            r = httpx.get(
                f"{_BASE}{path}",
                headers={"Authorization": f"Bearer {_tok}"},
                params=params or {},
                timeout=20,
            )
            if r.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"    429 → sleeping {wait}s (attempt {attempt + 1}/3)")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError:
            return None
        except Exception as e:
            print(f"    GET {path} error: {e}")
            return None
    return None


def search_cm(name: str) -> tuple[str | None, int | None]:
    """Returns (chartmetric_id, sp_monthly_listeners) for best match, or (None, None)."""
    d = _get("/search", {"q": name, "type": "artists", "limit": 1})
    artists = ((d or {}).get("obj") or {}).get("artists") or []
    if not artists:
        return None, None
    best = artists[0]
    return str(best.get("id", "")), best.get("sp_monthly_listeners")


def fetch_timeseries(cm_id: str, source: str, days: int) -> list[dict]:
    since = (date.today() - timedelta(days=days)).isoformat()
    d = _get(f"/artist/{cm_id}/stat/{source}", {"since": since})
    obj = (d or {}).get("obj") or []
    if not isinstance(obj, list):
        return []
    key = {
        "spotify": "listeners",
        "instagram": "followers",
        "tiktok": "followers",
        "youtube_channel": "subscribers",
    }.get(source, "value")
    result = []
    for pt in obj:
        ts = pt.get("timestp") or pt.get("date") or ""
        val = pt.get(key) or pt.get("value")
        if ts and val is not None:
            try:
                result.append({"date": str(ts)[:10], "value": int(float(val))})
            except (TypeError, ValueError):
                pass
    return sorted(result, key=lambda x: x["date"])


def compute_growth(ts: dict, sp_followers: int | None = None) -> dict:
    today = date.today()

    def past(pts, days_ago):
        target = (today - timedelta(days=days_ago)).isoformat()
        cands = [p for p in pts if p["date"] <= target]
        return cands[-1] if cands else None

    def pct(cur, prev):
        if prev and prev > 0:
            return round((cur - prev) / prev * 100, 2)
        return None

    feat: dict = {}

    sp = ts.get("spotify", [])
    if sp:
        cur = sp[-1]["value"]
        p30, p60, p90, p180 = past(sp, 30), past(sp, 60), past(sp, 90), past(sp, 180)
        for days_ago, key_name in [(30, "sp_30d"), (90, "sp_90d"), (180, "sp_180d")]:
            pv = {30: p30, 90: p90, 180: p180}[days_ago]
            g = pct(cur, pv["value"] if pv else None)
            if g is not None:
                feat[key_name] = g
        if p30 and p60:
            g_recent = pct(cur, p30["value"])
            g_prior = pct(p30["value"], p60["value"])
            if g_recent is not None and g_prior is not None:
                feat["sp_accel"] = round(g_recent - g_prior, 2)
        if sp_followers and sp_followers > 0:
            feat["sp_l2f_ratio"] = round(cur / sp_followers, 2)

    for source, prefix in [("instagram", "ig"), ("tiktok", "tk"), ("youtube_channel", "yt")]:
        pts = ts.get(source, [])
        if pts:
            cur = pts[-1]["value"]
            for days_ago, suffix in [(30, "30d"), (90, "90d")]:
                pv = past(pts, days_ago)
                g = pct(cur, pv["value"] if pv else None)
                if g is not None:
                    feat[f"{prefix}_{suffix}"] = g

    return feat


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Re-fetch timeseries even if already present")
    parser.add_argument("--days", type=int, default=180)
    args = parser.parse_args()

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    rows = (
        sb.schema("tinder").table("artist_cache")
        .select("slug, name, chartmetric_id, spotify_followers, cm_timeseries")
        .eq("lofi_booked", True)
        .execute().data or []
    )

    if not args.force:
        rows = [r for r in rows if not r.get("cm_timeseries")]

    total = len(rows)
    with_id = sum(1 for r in rows if r.get("chartmetric_id"))
    without_id = total - with_id
    est_sec = with_id * 4 * _RATE + without_id * 5 * _RATE
    print(f"\nLoFI-booked artists to process: {total}")
    print(f"  With chartmetric_id:    {with_id}  (~{with_id * 4 * _RATE / 60:.0f} min)")
    print(f"  Without chartmetric_id: {without_id}  (~{without_id * 5 * _RATE / 60:.0f} min, search included)")
    print(f"  Total estimated: ~{est_sec / 3600:.1f}h\n")

    _refresh()
    sources = ("spotify", "instagram", "tiktok", "youtube_channel")
    done = errors = 0
    start = time.time()

    for i, row in enumerate(rows, 1):
        name = row.get("name") or row["slug"]
        cm_id = row.get("chartmetric_id")
        sp_followers = row.get("spotify_followers")

        try:
            if not cm_id:
                cm_id, sp_listeners = search_cm(name)
                if not cm_id:
                    print(f"  [{i}/{total}] NOT FOUND: {name}")
                    errors += 1
                    continue
                sb.schema("tinder").table("artist_cache").update(
                    {"chartmetric_id": cm_id}
                ).eq("slug", row["slug"]).execute()

            ts: dict[str, list] = {}
            for source in sources:
                pts = fetch_timeseries(cm_id, source, args.days)
                if pts:
                    ts[source] = pts

            ml = compute_growth(ts, sp_followers) if ts else {}

            sb.schema("tinder").table("artist_cache").update({
                "chartmetric_id":            cm_id,
                "cm_timeseries":             ts or None,
                "ml_features":              ml or None,
                "cm_timeseries_updated_at": datetime.now(timezone.utc).isoformat(),
                "needs_enrichment":          False,
            }).eq("slug", row["slug"]).execute()

            done += 1
            sp_d = len(ts.get("spotify", []))
            ig_d = len(ts.get("instagram", []))
            tk_d = len(ts.get("tiktok", []))
            yt_d = len(ts.get("youtube_channel", []))
            elapsed = time.time() - start
            rate = elapsed / i
            eta_min = (total - i) * rate / 60
            print(f"  [{i}/{total}] {name:<30} SP:{sp_d}d IG:{ig_d}d TK:{tk_d}d YT:{yt_d}d  feat:{len(ml)}  ETA:{eta_min:.0f}m")

        except Exception as e:
            errors += 1
            print(f"  [{i}/{total}] ERROR {name}: {e}")

    elapsed = time.time() - start
    print(f"\nFinished in {elapsed / 60:.1f} min — {done} updated, {errors} errors")
    print("Run `python seed_timeseries.py` again to pick up any failed artists.")


if __name__ == "__main__":
    main()

"""
Per-artist chat dock — an artist insight & booking advisor (Phase 2).

Renders at the bottom of the Artist Profile page. Pre-loaded with the artist's
dashboard profile + (Phase 3) Lofi booking history, it answers booking questions
in Dutch, streams the response, and keeps a per-artist conversation.
"""
from __future__ import annotations

import streamlit as st

from agents.core import chat_stream, compliance_status
from scout.context import build_artist_view

# Quick-action chips — the high-value questions, one click for the team.
_CHIPS = [
    ("Goede boeking?",
     "Is dit een goede boeking voor LOFI? Geef een onderbouwd oordeel "
     "(ja/nee/twijfel) met de belangrijkste signalen."),
    ("Realistische gage?",
     "Wat is een realistische gage voor deze artiest, op basis van "
     "vergelijkbare eerdere LOFI-boekingen?"),
    ("Waarom groeit deze artiest?",
     "Leg in gewone taal uit waarom deze artiest groeit of juist afvlakt."),
    ("Vergelijkbaar met…",
     "Met welke referentie-artiesten en eerdere LOFI-boekingen is deze "
     "artiest vergelijkbaar, en waarom?"),
    ("Risico's",
     "Wat zijn de risico's of aandachtspunten bij het boeken van deze artiest?"),
    ("Teamnotitie",
     "Schrijf een korte interne notitie (3-4 zinnen) over deze artiest voor "
     "het boekingsteam."),
]


def render_artist_chat(artist_id: str, name: str, profile: dict,
                       ml: dict | None) -> None:
    st.divider()
    st.subheader("AI-assistent")

    status = compliance_status()
    if status["mode"] == "live":
        st.caption(f"AI actief — {status['model']}, regio "
                   f"{status['inference_geo']}. Vraag iets over {name}.")
    else:
        st.caption(f"Voorbeeldmodus — {status['reason']}. Zet LOFI_LLM_ENABLED "
                   "aan voor echte antwoorden.")

    view = build_artist_view(artist_id, name, profile, ml)
    if not view["booking_history"] and not view["comparables"]:
        st.caption("Airtable-boekingsdata nog niet gekoppeld — gage-vragen kan "
                   "ik nog niet beantwoorden.")

    # per-artist conversation history
    hist = st.session_state.setdefault("artist_chat", {}).setdefault(artist_id, [])
    for m in hist:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # quick-action chips
    clicked = None
    cols = st.columns(len(_CHIPS))
    for col, (label, question) in zip(cols, _CHIPS):
        if col.button(label, key=f"chip_{artist_id}_{label}"):
            clicked = question

    typed = st.chat_input(f"Stel een vraag over {name}…")
    user_msg = typed or clicked
    if not user_msg:
        return

    with st.chat_message("user"):
        st.markdown(user_msg)
    with st.chat_message("assistant"):
        try:
            full = st.write_stream(chat_stream(view, list(hist), user_msg))
        except Exception as e:  # noqa: BLE001 — surface LLM/config errors inline
            full = f"Er ging iets mis met de AI-assistent: {e}"
            st.error(full)

    hist.append({"role": "user", "content": user_msg})
    hist.append({"role": "assistant", "content": full})

import sys
import asyncio
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import os
import streamlit as st
from harmonai_pipeline import run_harmonai_pipeline_async, run_harmonai_pipeline_fast

st.set_page_config(
    page_title="HarmonAI",
    page_icon="assets/favicon.png" if os.path.exists("assets/favicon.png") else "🎵",
    layout="centered",
    initial_sidebar_state="collapsed",
)


def _parola_dogrula() -> bool:
    """
    APP_PASSWORD .env'de tanımlıysa basit bir parola ekranı gösterir.
    Tanımlı değilse (yerel geliştirme) korumasız çalışmaya devam eder.
    """
    beklenen = os.getenv("APP_PASSWORD")
    if not beklenen:
        return True
    if st.session_state.get("dogrulandi"):
        return True

    st.markdown('<p class="harmonai-title">HarmonAI</p>', unsafe_allow_html=True)
    girilen = st.text_input("Parola", type="password")
    if st.button("Giriş"):
        if girilen == beklenen:
            st.session_state["dogrulandi"] = True
            st.rerun()
        else:
            st.error("Yanlış parola.")
    return False


# ── Stil ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Ana başlık */
    .harmonai-title {
        font-size: 2.4rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        margin-bottom: 0;
    }
    .harmonai-sub {
        color: #888;
        font-size: 0.95rem;
        margin-top: 0.1rem;
        margin-bottom: 1.8rem;
    }

    /* Akor badge'leri */
    .chord-badge {
        display: inline-block;
        background: #1e1e2e;
        color: #cdd6f4;
        border: 1px solid #313244;
        border-radius: 8px;
        padding: 4px 12px;
        margin: 3px 3px;
        font-family: monospace;
        font-size: 0.95rem;
        font-weight: 600;
    }
    .chord-badge-web {
        background: #1e2e1e;
        color: #a6e3a1;
        border-color: #2a4a2a;
    }

    /* Rapor kutusu */
    .report-box {
        background: #111118;
        border: 1px solid #2a2a3a;
        border-radius: 12px;
        padding: 1.4rem 1.6rem;
        margin-top: 0.5rem;
        line-height: 1.75;
        font-size: 0.95rem;
    }

    /* Bölüm başlıkları */
    .section-label {
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #888;
        margin-bottom: 0.5rem;
    }

    /* Metric kartları için ince ayar */
    [data-testid="metric-container"] {
        background: #111118;
        border: 1px solid #2a2a3a;
        border-radius: 10px;
        padding: 1rem;
    }
</style>
""", unsafe_allow_html=True)

if not _parola_dogrula():
    st.stop()

# ── Başlık ────────────────────────────────────────────────────────────────────
st.markdown('<p class="harmonai-title">HarmonAI</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="harmonai-sub">AI-powered harmonic analysis — key, mode, chords & musicological report</p>',
    unsafe_allow_html=True,
)

st.divider()

# ── Giriş Formu ───────────────────────────────────────────────────────────────
youtube_url = st.text_input(
    "YouTube Link",
    placeholder="https://www.youtube.com/watch?v=...",
    label_visibility="visible",
)

col_artist, col_title = st.columns(2)
with col_artist:
    artist_name = st.text_input("Artist", placeholder="e.g. Radiohead")
with col_title:
    song_title = st.text_input("Song Title", placeholder="e.g. Creep")

col_lang, col_mode = st.columns(2)
with col_lang:
    language = st.selectbox(
        "Language",
        options=["tr", "en"],
        format_func=lambda x: "Turkish" if x == "tr" else "Western / English",
    )
with col_mode:
    analiz_modu = st.selectbox(
        "Analysis Mode",
        options=["fast", "full"],
        format_func=lambda x: "Fast  (librosa, ~10s)" if x == "fast" else "Full  (Basic Pitch + MIDI, ~2-3min)",
    )

# Mod açıklaması
if analiz_modu == "fast":
    st.caption("Fast mode uses direct chroma extraction via librosa. No MIDI conversion — results in seconds.")
else:
    st.caption("Full mode converts audio to MIDI via Basic Pitch CNN, then runs harmonic analysis. More accurate, slower.")

st.divider()

# ── Analiz Butonu ─────────────────────────────────────────────────────────────
run = st.button("Analyze", use_container_width=True, type="primary")

if run:
    if not youtube_url or not artist_name or not song_title:
        st.warning("Please fill in all fields before running the analysis.")
    else:
        sure_tahmini = "~10 seconds" if analiz_modu == "fast" else "~2-3 minutes"
        hata_detay = None
        with st.spinner(f"Running analysis ({sure_tahmini})..."):
            try:
                if analiz_modu == "fast":
                    sonuc = asyncio.run(run_harmonai_pipeline_fast(youtube_url, artist_name, song_title, language))
                else:
                    sonuc = asyncio.run(run_harmonai_pipeline_async(youtube_url, artist_name, song_title))
            except Exception as e:
                sonuc = None
                hata_detay = str(e)

        basarisiz = sonuc is None or (isinstance(sonuc, dict) and "error" in sonuc and "final_report" not in sonuc)

        if basarisiz:
            mesaj = sonuc.get("error") if isinstance(sonuc, dict) else None
            st.error(mesaj or "Analysis failed. Check the YouTube link or song details and try again.")
            if hata_detay:
                st.error(f"Teknik detay: {hata_detay}")
        else:
            st.success("Analysis complete.")

            # ── Metrikler ────────────────────────────────────────────────────
            col1, col2, col3 = st.columns(3)
            col1.metric("Key / Mode", f"{sonuc['detected_key']} {sonuc['detected_mode']}")
            col2.metric("Tempo", f"{int(sonuc['tempo'])} BPM")
            col3.metric("Unique Chords", len(sonuc['final_chords']))

            # ── Tespit edilen akorlar ─────────────────────────────────────────
            st.markdown('<p class="section-label">Detected Chords</p>', unsafe_allow_html=True)
            badges = "".join(
                f'<span class="chord-badge">{c}</span>'
                for c in sonuc['final_chords']
            )
            st.markdown(badges, unsafe_allow_html=True)

            # ── Web'den çekilen akorlar ───────────────────────────────────────
            if sonuc['web_chords'].get('success'):
                st.markdown('<p class="section-label" style="margin-top:1rem">Web Chords</p>', unsafe_allow_html=True)
                source = sonuc['web_chords'].get('source_url', '')
                if source:
                    st.caption(f"Source: {source}")
                web_badges = "".join(
                    f'<span class="chord-badge chord-badge-web">{c}</span>'
                    for c in sonuc['web_chords']['unique_chords']
                )
                st.markdown(web_badges, unsafe_allow_html=True)
            else:
                st.caption("Web chord lookup returned no results.")

            # ── HarmonAI Raporu ───────────────────────────────────────────────
            st.markdown('<p class="section-label" style="margin-top:1.5rem">HarmonAI Report</p>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="report-box">{sonuc["final_report"]}</div>',
                unsafe_allow_html=True,
            )

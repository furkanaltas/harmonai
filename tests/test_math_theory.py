"""math_theory çekirdek fonksiyonları için deterministik birim testleri.

Çalıştırma: python -m pytest tests/ -v
"""

import numpy as np

from modules.math_theory import (
    PROFILES_V3,
    estimate_mode_v3,
    identify_complex_chord,
)


# ── estimate_mode_v3 ──────────────────────────────────────────────────────────

def test_major_profil_c_major_olarak_taninir():
    # Major profilinin kendisi chroma olarak verilirse korelasyon i=0'da 1.0 olur
    chroma = np.array(PROFILES_V3["Major"], dtype=float)
    key, mode = estimate_mode_v3(chroma)
    assert (key, mode) == ("C", "Major")


def test_9_kaydirilmis_minor_profil_a_minor_olarak_taninir():
    # Minor profili 9 yarım ses kaydırılırsa tonik A'ya taşınır (A Minor)
    chroma = np.roll(np.array(PROFILES_V3["Minor"], dtype=float), 9)
    key, mode = estimate_mode_v3(chroma)
    assert (key, mode) == ("A", "Minor")


def test_sessizlik_bilinmiyor_dondurur():
    key, mode = estimate_mode_v3(np.zeros(12))
    assert key == "Bilinmiyor" and mode == "Bilinmiyor"


def test_harmonic_minor_profili_yukseltilmis_yediliyi_agirliklandirir():
    # Kalibrasyon regresyon testi: Harmonic Minor'da leading tone (idx 11)
    # doğal m7'den (idx 10) yüksek olmalı — bu ters yazılmıştı ve düzeltildi.
    profil = PROFILES_V3["Harmonic Minor"]
    assert profil[11] > profil[10]


def test_hicaz_profili_m3_dislar():
    # Hicaz gamında doğal m3 (idx 3) yoktur; karakteristik M3 (idx 4) baskın olmalı.
    profil = PROFILES_V3["Hicaz"]
    assert profil[4] > profil[3]


# ── identify_complex_chord ────────────────────────────────────────────────────

def test_c_major_triadi_c_olarak_taninir():
    v = np.zeros(12)
    v[[0, 4, 7]] = 1.0  # C, E, G
    assert identify_complex_chord(v) == "C"


def test_a_minor_triadi_am_olarak_taninir():
    v = np.zeros(12)
    v[[9, 0, 4]] = 1.0  # A, C, E
    assert identify_complex_chord(v) == "Am"


def test_bos_vektor_none_dondurur():
    assert identify_complex_chord(np.zeros(12)) is None


def test_gecersiz_key_mode_cokme_yaratmaz():
    # Bilinmeyen key/mode verildiğinde bonus atlanır ama tespit yine çalışır
    v = np.zeros(12)
    v[[0, 4, 7]] = 1.0
    sonuc = identify_complex_chord(v, detected_key="X#", detected_mode="Major")
    assert sonuc == "C"

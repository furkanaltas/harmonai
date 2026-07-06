"""math_theory çekirdek fonksiyonları için deterministik birim testleri.

Çalıştırma: python -m pytest tests/ -v
"""

import numpy as np

from modules.math_theory import (
    PROFILES_V3,
    estimate_mode_v3,
    estimate_mode_v3_adaylar,
    tie_break_key,
    weighted_chroma_average,
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


# ── aday listesi & tie-break ──────────────────────────────────────────────────

def test_locrian_profili_kaldirildi():
    # Locrian, ground truth'ta hiç görülmediği halde yanlış pozitif üretiyordu
    assert "Locrian" not in PROFILES_V3


def test_adaylar_sirali_ve_ilk_aday_dogru():
    chroma = np.array(PROFILES_V3["Major"], dtype=float)
    adaylar = estimate_mode_v3_adaylar(chroma, top_n=2)
    assert len(adaylar) == 2
    assert adaylar[0][:2] == ("C", "Major")
    assert adaylar[0][2] >= adaylar[1][2]


def test_adaylar_sessizlikte_bos():
    assert estimate_mode_v3_adaylar(np.zeros(12)) == []


def test_tie_break_dominant_major_kaniti_minoru_secer():
    # Skorlar çok yakın; dizide Am tonik baskın + E majör dominant + son akor Am
    adaylar = [("C", "Major", 0.900), ("A", "Minor", 0.895)]
    seq = ["Am", "E", "Am", "F", "E", "Am"]
    assert tie_break_key(adaylar, seq) == ("A", "Minor")


def test_tie_break_buyuk_margin_ilk_adayi_korur():
    # Margin eşikten büyükse akor kanıtına hiç bakılmaz
    adaylar = [("C", "Major", 0.95), ("A", "Minor", 0.80)]
    seq = ["Am", "E", "Am"]
    assert tie_break_key(adaylar, seq) == ("C", "Major")


def test_tie_break_bos_dizide_ilk_adayi_korur():
    adaylar = [("C", "Major", 0.90), ("A", "Minor", 0.895)]
    assert tie_break_key(adaylar, []) == ("C", "Major")


# ── weighted_chroma_average ───────────────────────────────────────────────────

def test_agirlikli_ortalama_son_bolumu_vurgular():
    # İlk 85 kare yalnızca C (idx 0), son 15 kare yalnızca A (idx 9).
    # Ağırlıklı ortalamada A'nın payı düz ortalamadan yüksek olmalı.
    m = np.zeros((12, 100))
    m[0, :85] = 1.0
    m[9, 85:] = 1.0
    duz = m.mean(axis=1)
    agirlikli = weighted_chroma_average(m)
    assert agirlikli[9] > duz[9]
    assert agirlikli[0] < duz[0]


def test_agirlikli_ortalama_tekduze_matriste_ortalamaya_esit():
    # Zamana göre değişmeyen matriste ağırlıklandırma sonucu değiştirmemeli
    m = np.tile(np.arange(12, dtype=float).reshape(12, 1), (1, 50))
    assert np.allclose(weighted_chroma_average(m), m.mean(axis=1))

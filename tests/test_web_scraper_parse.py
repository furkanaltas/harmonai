"""web_scraper akor ayıklama (_parse_chords) için birim testleri.

Çalıştırma: python -m pytest tests/ -v
"""

from modules.web_scraper import _parse_chords


def test_bracket_notasyonu_oncelikli():
    text = "intro [Am] devam [F] sonra [C] final [G7]"
    assert _parse_chords(text) == ["Am", "F", "C", "G7"]


def test_bracket_tekrarlari_teklestirilir():
    text = "[Am] [Am] [F] [Am] [F]"
    assert _parse_chords(text) == ["Am", "F"]


def test_akor_yogun_satir_taranir():
    text = "Şarkı sözleri satırı burada\nAm F C G\nbaşka bir söz satırı"
    assert _parse_chords(text) == ["Am", "F", "C", "G"]


def test_duz_metindeki_tek_harfler_akor_sayilmaz():
    # İngilizce cümledeki 'A' ve 'C' gürültüdür — genel taramada elenmeli
    text = "A quick brown fox jumps over the lazy dog near C street"
    assert _parse_chords(text) == []


def test_gecersiz_akor_adlari_filtrelenir():
    text = "[Hm] [Xm7] [Am]"  # Hm ve Xm7 geçerli kök değil
    assert _parse_chords(text) == ["Am"]

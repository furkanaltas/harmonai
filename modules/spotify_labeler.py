"""
spotify_labeler.py — HarmonAI Spotify Veri Etiketleyici
=========================================================

AMAÇ:
    veri_seti/ klasöründeki MIDI dosyalarını Spotify API üzerinden
    ton (key) ve mod (mode) bilgileriyle etiketleyip dataset.db'ye kaydeder.

KULLANIM:
    python spotify_labeler.py                    # Tüm klasörü tara
    python spotify_labeler.py --klasor veri_seti/Midi\ Çıktıları/Türkçe
    python spotify_labeler.py --yeniden-etiketle # unknown kayıtları yeniden dene
"""

import os
import re
import sys
import time
import argparse
import glob
from pathlib import Path
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

from modules.db_manager import db_init, db_get_or_create_song, db_update_spotify, db_song_label

# ── Yapılandırma ──────────────────────────────────────────────────────────────

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_KLASOR: str = os.path.join(_ROOT, "veri_seti")

PITCH_CLASS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
MOD_ADI = {0: "minor", 1: "major"}

API_BEKLEME_SN: float = 0.6
MAX_DENEME: int = 3


# ── Dosya Ayrıştırma ──────────────────────────────────────────────────────────

def dosya_ayristry(dosya_yolu: str) -> tuple[str, str]:
    """
    "Sanatçı-Şarkı Adı_davulsuz.mid" → ("Sanatçı", "Şarkı Adı")

    Kurallar:
    - Uzantı ve "_davulsuz" / "_davulsuz_N" son eki temizlenir.
    - İlk tire (-) sanatçı / şarkı ayırıcısıdır.
    - Sanatçı veya şarkı adı içindeki tireler korunur (örn. "Barış Manço-Hal Hal").
    """
    dosya_adi = Path(dosya_yolu).stem  # uzantısız ad

    # "_davulsuz" ve sonrasını kaldır (örn. "_davulsuz_2")
    temiz = re.sub(r'_davulsuz.*$', '', dosya_adi, flags=re.IGNORECASE).strip()

    # İlk tire pozisyonundan böl
    parca = temiz.split('-', 1)
    if len(parca) == 2:
        artist = parca[0].strip()
        title  = parca[1].strip()
    else:
        artist = ""
        title  = temiz.strip()

    return artist, title


# ── Spotify API ───────────────────────────────────────────────────────────────

def spotify_baglanti() -> Optional[spotipy.Spotify]:
    load_dotenv()
    client_id     = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("[HATA] SPOTIPY_CLIENT_ID veya SPOTIPY_CLIENT_SECRET .env dosyasında bulunamadı.")
        return None

    try:
        auth = SpotifyClientCredentials(client_id=client_id, client_secret=client_secret)
        return spotipy.Spotify(auth_manager=auth, requests_timeout=10)
    except Exception as e:
        print(f"[HATA] Spotify bağlantısı kurulamadı: {e}")
        return None


def spotify_sorgula(
    sp: spotipy.Spotify,
    artist: str,
    title: str,
) -> tuple[Optional[int], Optional[int], str]:
    """
    Spotify'dan (key, mode, label) döndürür.
    Bulunamazsa (None, None, "unknown") döner.
    """
    sorgu = f"track:{title}"
    if artist:
        sorgu += f" artist:{artist}"

    for deneme in range(1, MAX_DENEME + 1):
        try:
            sonuclar = sp.search(q=sorgu, type="track", limit=1, market="TR")
            parcalar = sonuclar.get("tracks", {}).get("items", [])

            if not parcalar:
                return None, None, "unknown"

            track_id = parcalar[0]["id"]
            time.sleep(API_BEKLEME_SN)

            ozellikler = sp.audio_features([track_id])
            if not ozellikler or ozellikler[0] is None:
                return None, None, "unknown"

            key  = ozellikler[0]["key"]    # 0-11
            mode = ozellikler[0]["mode"]   # 0=minör, 1=majör

            if key == -1:  # Spotify bazen -1 döner (tespit edilemedi)
                return None, None, "unknown"

            nota = PITCH_CLASS[key]
            label = f"{nota}_{MOD_ADI.get(mode, 'unknown')}"
            return key, mode, label

        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 429:
                bekleme = int(e.headers.get("Retry-After", 10)) if e.headers else 10
                print(f"   [Rate Limit] {bekleme}s bekleniyor...")
                time.sleep(bekleme)
            else:
                print(f"   [Spotify Hatası] {e.http_status}: {e.msg}")
                return None, None, "unknown"

        except Exception as e:
            if deneme < MAX_DENEME:
                time.sleep(deneme * 2)
            else:
                print(f"   [Bağlantı Hatası] {e}")
                return None, None, "unknown"

    return None, None, "unknown"


# ── Ana Akış ──────────────────────────────────────────────────────────────────

def midi_dosyalarini_bul(klasor: str) -> list[str]:
    """Klasör ve alt klasörlerdeki tüm .mid / .midi dosyalarını bulur."""
    pattern_mid  = os.path.join(klasor, "**", "*.mid")
    pattern_midi = os.path.join(klasor, "**", "*.midi")
    dosyalar = glob.glob(pattern_mid, recursive=True) + glob.glob(pattern_midi, recursive=True)
    return sorted(set(dosyalar))


def etiketle(
    klasor: str = VARSAYILAN_KLASOR,
    yeniden_etiketle: bool = False,
) -> None:
    """
    Ana etiketleme pipeline'ı.

    Parametreler:
        klasor           : Taranacak MIDI klasörü
        yeniden_etiketle : True ise "unknown" kayıtlar da yeniden denenir
    """
    sp = spotify_baglanti()
    if not sp:
        sys.exit(1)

    db_init()

    dosyalar = midi_dosyalarini_bul(klasor)
    if not dosyalar:
        print(f"[UYARI] '{klasor}' içinde MIDI dosyası bulunamadı.")
        return

    # Klasör adından dil tahmini (Türkçe / Yabancı klasör adına göre)
    dil = "tr" if "türkçe" in klasor.lower() or "turkce" in klasor.lower() else \
          "en" if "yabancı" in klasor.lower() or "yabanci" in klasor.lower() else "unknown"

    toplam    = len(dosyalar)
    basarili  = 0
    bulunamayan = 0
    atlanan   = 0

    print("=" * 60)
    print("HarmonAI Spotify Etiketleyici")
    print(f"Klasör  : {klasor}")
    print(f"Toplam  : {toplam} dosya")
    print("=" * 60)

    for idx, dosya_yolu in enumerate(dosyalar, start=1):
        dosya_adi = os.path.basename(dosya_yolu)
        artist, title = dosya_ayristry(dosya_yolu)

        # songs tablosuna ekle / güncelle — song_id al
        song_id = db_get_or_create_song(
            filename=dosya_adi,
            artist=artist,
            title=title,
            language=dil,
            midi_path=dosya_yolu,
        )

        # Daha önce başarıyla etiketlenmişse atla
        if not yeniden_etiketle:
            mevcut_label = db_song_label(song_id)
            if mevcut_label and mevcut_label != "unknown":
                print(f"[{idx:>4}/{toplam}] Atlandı (zaten etiketli): {dosya_adi[:55]}")
                atlanan += 1
                continue

        print(f"[{idx:>4}/{toplam}] Sorgulanıyor: {artist} - {title}")

        key, mode, label = spotify_sorgula(sp, artist, title)
        db_update_spotify(dosya_adi, key, mode, label)

        if label != "unknown":
            basarili += 1
            print(f"         ✅ {label}")
        else:
            bulunamayan += 1
            print(f"         ⚠️  Spotify'da bulunamadı: {dosya_adi}")

        time.sleep(API_BEKLEME_SN)

    print("\n" + "=" * 60)
    print("ETİKETLEME TAMAMLANDI")
    print(f"  Toplam taranan dosya  : {toplam}")
    print(f"  Başarıyla etiketlenen : {basarili}")
    print(f"  Bulunamayan (unknown) : {bulunamayan}")
    print(f"  Atlandı (zaten var)   : {atlanan}")
    print("=" * 60)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="HarmonAI Spotify Etiketleyici",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python spotify_labeler.py
  python spotify_labeler.py --klasor "veri_seti/Midi Çıktıları/Türkçe"
  python spotify_labeler.py --yeniden-etiketle
        """
    )
    parser.add_argument(
        "--klasor",
        default=VARSAYILAN_KLASOR,
        help=f"Taranacak MIDI klasörü (varsayılan: {VARSAYILAN_KLASOR})"
    )
    parser.add_argument(
        "--yeniden-etiketle",
        action="store_true",
        help="'unknown' olarak kayıtlı şarkıları yeniden dene"
    )

    args = parser.parse_args()
    etiketle(klasor=args.klasor, yeniden_etiketle=args.yeniden_etiketle)

"""
midi_labeler.py — MIDI dosyalarından otomatik key/mode etiketleyici
====================================================================

Spotify audio-features API artık yeni uygulamalara kapalı olduğundan,
bu modül veri_seti/ içindeki MIDI dosyalarını kendi math_theory
modülümüzle analiz ederek songs tablosunu etiketler.

KULLANIM:
    python modules/midi_labeler.py
    python modules/midi_labeler.py --yeniden-etiketle
    python modules/midi_labeler.py --klasor veri_seti/Türkçe
"""

import os
import sys
import glob
import argparse
import re
from pathlib import Path

import numpy as np
import pretty_midi

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.math_theory import estimate_mode_v3
from modules.db_manager import db_init, db_get_or_create_song, db_update_spotify, db_song_label

VARSAYILAN_KLASOR = os.path.join(_ROOT, "veri_seti")
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _dil_tespiti(klasor_yolu: str) -> str:
    k = klasor_yolu.lower()
    if "türkçe" in k or "turkce" in k:
        return "tr"
    if "yabancı" in k or "yabanci" in k:
        return "en"
    return "unknown"


def _dosya_ayristir(dosya_yolu: str) -> tuple[str, str]:
    """'Sanatçı-Şarkı_davulsuz.mid' → ('Sanatçı', 'Şarkı')"""
    stem = Path(dosya_yolu).stem
    temiz = re.sub(r'_davulsuz.*$', '', stem, flags=re.IGNORECASE).strip()
    parca = temiz.split('-', 1)
    if len(parca) == 2:
        return parca[0].strip(), parca[1].strip()
    return "", temiz.strip()


def midi_key_tespit(midi_yolu: str) -> tuple[str, str]:
    """MIDI dosyasından chroma ortalaması → key ve mode döndürür."""
    pm = pretty_midi.PrettyMIDI(midi_yolu)
    chroma = pm.get_chroma().mean(axis=1)
    return estimate_mode_v3(chroma)


def etiketle(klasor: str = VARSAYILAN_KLASOR, yeniden_etiketle: bool = False) -> None:
    db_init()

    dosyalar = sorted(set(
        glob.glob(os.path.join(klasor, "**", "*.mid"),  recursive=True) +
        glob.glob(os.path.join(klasor, "**", "*.midi"), recursive=True)
    ))

    if not dosyalar:
        print(f"[UYARI] '{klasor}' içinde MIDI dosyası bulunamadı.")
        return

    toplam   = len(dosyalar)
    basarili = 0
    atlanan  = 0
    hatali   = 0

    print("=" * 60)
    print("HarmonAI MIDI Otomatik Etiketleyici")
    print(f"Klasör : {klasor}")
    print(f"Toplam : {toplam} dosya")
    print("=" * 60)

    for idx, dosya_yolu in enumerate(dosyalar, start=1):
        dosya_adi = os.path.basename(dosya_yolu)
        artist, title = _dosya_ayristir(dosya_yolu)
        dil = _dil_tespiti(os.path.dirname(dosya_yolu))

        song_id = db_get_or_create_song(
            filename=dosya_adi,
            artist=artist,
            title=title,
            language=dil,
            midi_path=dosya_yolu,
        )

        if not yeniden_etiketle:
            mevcut = db_song_label(song_id)
            if mevcut and mevcut != "unknown":
                print(f"[{idx:>4}/{toplam}] Atlandı : {dosya_adi[:55]}")
                atlanan += 1
                continue

        try:
            key_str, mode_str = midi_key_tespit(dosya_yolu)

            if key_str in ("Bilinmiyor", "") or mode_str in ("Bilinmiyor", ""):
                print(f"[{idx:>4}/{toplam}] ⚠  Tespit edilemedi : {dosya_adi[:50]}")
                hatali += 1
                continue

            try:
                key_idx = NOTE_NAMES.index(key_str)
            except ValueError:
                key_idx = None

            label = f"{key_str}_{mode_str}"
            db_update_spotify(dosya_adi, key_idx, None, label)

            print(f"[{idx:>4}/{toplam}] OK  {artist or '?':20s} - {title[:25]:25s}  →  {label}")
            basarili += 1

        except Exception as e:
            print(f"[{idx:>4}/{toplam}] HATA: {dosya_adi[:45]} — {e}")
            hatali += 1

    print()
    print("=" * 60)
    print(f"Tamamlandı — Etiketlendi: {basarili}  |  Atlandı: {atlanan}  |  Hata: {hatali}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MIDI tabanlı otomatik key/mode etiketleyici")
    parser.add_argument("--klasor", default=VARSAYILAN_KLASOR, help="Taranacak klasör")
    parser.add_argument("--yeniden-etiketle", action="store_true", help="Zaten etiketlileri de yeniden işle")
    args = parser.parse_args()

    etiketle(klasor=args.klasor, yeniden_etiketle=args.yeniden_etiketle)

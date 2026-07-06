"""
ground_truth_tool.py — Elle ground truth doğrulama aracı
============================================================

AMAÇ:
    Self-labeling döngüsünü kırmak için rastgele bir örneklemi (30-50 şarkı)
    kör (blind) şekilde CSV'ye çıkarır — sistemin kendi tahminini göstermez.
    Kulakla doğrulanan etiketler geri yüklendiğinde gerçek doğruluk oranı
    ve yanlış tahmin listesi üretir.

KULLANIM:
    python modules/ground_truth_tool.py --export 40
        -> ground_truth_worksheet.csv oluşturur

    (CSV'yi elle doldur: manual_key ve manual_mode kolonları)

    python modules/ground_truth_tool.py --import-csv ground_truth_worksheet.csv
        -> DB'ye yazar, doğruluk raporunu basar
"""

import os
import sys
import csv
import argparse
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from modules.db_manager import (
    db_init,
    db_random_sample_for_ground_truth,
    db_set_ground_truth,
    db_ground_truth_accuracy,
)

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
MODES = ['Major', 'Minor', 'Harmonic Minor', 'Melodic Minor', 'Hicaz',
         'Dorian', 'Phrygian (Kürdi)', 'Mixolydian', 'Locrian', 'Lydian']

_MODE_ALIASES = {
    'major': 'Major', 'maj': 'Major',
    'minor': 'Minor', 'min': 'Minor',
    'harmonic minor': 'Harmonic Minor', 'harmonicminor': 'Harmonic Minor', 'hminor': 'Harmonic Minor',
    'melodic minor': 'Melodic Minor', 'melodicminor': 'Melodic Minor', 'mminor': 'Melodic Minor',
    'hicaz': 'Hicaz',
    'dorian': 'Dorian',
    'phrygian': 'Phrygian (Kürdi)', 'kurdi': 'Phrygian (Kürdi)', 'kürdi': 'Phrygian (Kürdi)',
    'mixolydian': 'Mixolydian',
    'locrian': 'Locrian',
    'lydian': 'Lydian',
}

_FLAT_TO_SHARP = {'DB': 'C#', 'EB': 'D#', 'GB': 'F#', 'AB': 'G#', 'BB': 'A#'}

WORKSHEET_PATH = os.path.join(_ROOT, "ground_truth_worksheet.csv")


def _normalize_mode(ham: str) -> str:
    key = ham.strip().lower()
    if key not in _MODE_ALIASES:
        raise ValueError(f"Bilinmeyen mod: '{ham}'. Geçerli modlar: {MODES}")
    return _MODE_ALIASES[key]


def _normalize_key(ham: str) -> str:
    nota = ham.strip().upper()
    nota = _FLAT_TO_SHARP.get(nota, nota)
    if nota not in NOTE_NAMES:
        raise ValueError(f"Bilinmeyen nota: '{ham}'. Geçerli notalar: {NOTE_NAMES}")
    return nota


def export_worksheet(n: int) -> None:
    db_init()
    songs = db_random_sample_for_ground_truth(n)

    if not songs:
        print("[UYARI] Örneklenecek şarkı bulunamadı (hepsi zaten doğrulanmış olabilir).")
        return

    # Mevcut (muhtemelen elle doldurulmuş) worksheet'i asla ezme —
    # dosya varsa timestamp'li yeni bir ad kullan.
    hedef_yol = WORKSHEET_PATH
    if os.path.exists(hedef_yol):
        zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
        hedef_yol = os.path.join(_ROOT, f"ground_truth_worksheet_{zaman}.csv")
        print(f"[UYARI] Mevcut worksheet korunuyor — yeni dosya: {os.path.basename(hedef_yol)}")

    with open(hedef_yol, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["song_id", "artist", "title", "midi_path", "manual_key", "manual_mode"])
        for s in songs:
            rel_path = os.path.relpath(s["midi_path"], _ROOT)
            writer.writerow([s["id"], s["artist"], s["title"], rel_path, "", ""])

    print(f"[OK] {len(songs)} şarkı '{hedef_yol}' dosyasına yazıldı.")
    print(f"     manual_key   -> {NOTE_NAMES}")
    print(f"     manual_mode  -> {MODES}")
    print("     Not: Sistem tahmini bilerek gösterilmedi (kör test — önyargı olmasın diye).")


def import_worksheet(path: str) -> None:
    db_init()

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    islenen = 0
    atlanan = 0

    for row in rows:
        manual_key = row.get("manual_key", "").strip()
        manual_mode = row.get("manual_mode", "").strip()

        if not manual_key or not manual_mode:
            atlanan += 1
            continue

        try:
            key = _normalize_key(manual_key)
            mode = _normalize_mode(manual_mode)
        except ValueError as e:
            print(f"[HATA] song_id={row['song_id']}: {e}")
            atlanan += 1
            continue

        db_set_ground_truth(int(row["song_id"]), f"{key}_{mode}")
        islenen += 1

    print(f"[OK] {islenen} şarkı ground truth ile güncellendi, {atlanan} atlandı (boş/hatalı).\n")

    rapor = db_ground_truth_accuracy()
    print("=" * 60)
    print("Ground Truth Doğruluk Raporu")
    print("=" * 60)
    print(f"Toplam doğrulanmış : {rapor['toplam']}")
    print(f"Doğru tahmin       : {rapor['dogru']}")
    print(f"Doğruluk oranı     : %{rapor['oran']}")
    if rapor["yanlislar"]:
        print("\nYanlış tahminler:")
        for y in rapor["yanlislar"]:
            print(f"  {y['artist']} - {y['title']}: sistem={y['label']}  insan={y['ground_truth_label']}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Elle ground truth doğrulama aracı")
    parser.add_argument("--export", type=int, metavar="N", help="N adet rastgele şarkıyı CSV'ye aktar")
    parser.add_argument("--import-csv", dest="import_csv", metavar="PATH", help="Doldurulmuş CSV'yi DB'ye işle ve doğruluk raporu al")
    args = parser.parse_args()

    if args.export:
        export_worksheet(args.export)
    elif args.import_csv:
        import_worksheet(args.import_csv)
    else:
        parser.print_help()

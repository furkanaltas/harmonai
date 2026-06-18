"""
db_manager.py — HarmonAI SQLite Veritabanı Yöneticisi
=======================================================

Tablo yapısı:
    songs     : Şarkı metadata + Spotify ground truth
    analyses  : Her analiz çalışmasının sonuçları (key_correct dahil)

Kullanım:
    from modules.db_manager import db_get_or_create_song, db_save_analysis, db_summary
"""

import json
import sqlite3
import os
from datetime import datetime
from typing import Optional

DB_YOLU: str = os.path.join(os.path.dirname(__file__), "..", "dataset.db")


# ── Bağlantı ──────────────────────────────────────────────────────────────────

def _baglanti() -> sqlite3.Connection:
    con = sqlite3.connect(DB_YOLU)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def db_init() -> None:
    """Tablolar yoksa oluşturur. Varsa dokunmaz."""
    with _baglanti() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS songs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                filename      TEXT    NOT NULL UNIQUE,
                artist        TEXT,
                title         TEXT,
                language      TEXT    CHECK(language IN ('tr','en','unknown')) DEFAULT 'unknown',
                midi_path     TEXT,
                spotify_key   INTEGER,
                spotify_mode  INTEGER,
                label         TEXT    DEFAULT 'unknown'
            );

            CREATE TABLE IF NOT EXISTS analyses (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                song_id        INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
                analyzed_at    TEXT    NOT NULL,
                analyzer       TEXT    CHECK(analyzer IN ('fast','full')) DEFAULT 'fast',
                detected_key   TEXT,
                detected_mode  TEXT,
                tempo          REAL,
                chords         TEXT,
                chord_sequence TEXT,
                web_chords     TEXT,
                web_source_url TEXT,
                key_correct    INTEGER CHECK(key_correct IN (0,1))
            );

            CREATE INDEX IF NOT EXISTS idx_analyses_song_id ON analyses(song_id);
        """)
    print("[DB] Tablolar hazır.")


# ── songs tablosu ─────────────────────────────────────────────────────────────

def db_get_or_create_song(
    filename: str,
    artist: str = "",
    title: str = "",
    language: str = "unknown",
    midi_path: str = "",
) -> int:
    """
    Dosya adına göre songs tablosunda satır bul veya oluştur.
    song_id (int) döndürür.
    """
    with _baglanti() as con:
        satir = con.execute(
            "SELECT id FROM songs WHERE filename = ?", (filename,)
        ).fetchone()

        if satir:
            # midi_path güncelle (dosya taşınmış olabilir)
            con.execute(
                "UPDATE songs SET midi_path = ?, language = ? WHERE id = ?",
                (midi_path, language, satir["id"])
            )
            return satir["id"]

        cur = con.execute(
            """INSERT INTO songs (filename, artist, title, language, midi_path)
               VALUES (?, ?, ?, ?, ?)""",
            (filename, artist, title, language, midi_path)
        )
        return cur.lastrowid


def db_update_spotify(
    filename: str,
    spotify_key: Optional[int],
    spotify_mode: Optional[int],
    label: str,
) -> None:
    """spotify_labeler.py tarafından çağrılır — Spotify ground truth günceller."""
    with _baglanti() as con:
        con.execute(
            """UPDATE songs
               SET spotify_key = ?, spotify_mode = ?, label = ?
               WHERE filename = ?""",
            (spotify_key, spotify_mode, label, filename)
        )


# ── analyses tablosu ──────────────────────────────────────────────────────────

def db_save_analysis(
    song_id: int,
    analyzer: str,
    detected_key: str,
    detected_mode: str,
    tempo: float,
    chords: list[str],
    chord_sequence: list[str],
    web_chords: dict,
) -> int:
    """
    Analiz sonucunu kaydeder. Spotify ground truth varsa key_correct hesaplar.

    Döndürür: analysis_id (int)
    """
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

    with _baglanti() as con:
        # Ground truth var mı kontrol et
        spotify_satir = con.execute(
            "SELECT spotify_key FROM songs WHERE id = ?", (song_id,)
        ).fetchone()

        key_correct = None
        if spotify_satir and spotify_satir["spotify_key"] is not None:
            spotify_nota = NOTE_NAMES[spotify_satir["spotify_key"]]
            key_correct = 1 if spotify_nota == detected_key else 0

        cur = con.execute(
            """INSERT INTO analyses
               (song_id, analyzed_at, analyzer, detected_key, detected_mode,
                tempo, chords, chord_sequence, web_chords, web_source_url, key_correct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                song_id,
                datetime.now().isoformat(timespec="seconds"),
                analyzer,
                detected_key,
                detected_mode,
                round(tempo, 2),
                json.dumps(chords, ensure_ascii=False),
                json.dumps(chord_sequence[:500], ensure_ascii=False),  # ilk 500 eleman
                json.dumps(web_chords.get("unique_chords", []), ensure_ascii=False),
                web_chords.get("source_url"),
                key_correct,
            )
        )
        return cur.lastrowid


def db_get_existing_songs() -> list[str]:
    """
    DB'deki tüm şarkıları "artist - title" formatında döndürür.
    Gemini prompt'una geçmek için kullanılır (tekrar üretimi önler).
    """
    with _baglanti() as con:
        satirlar = con.execute(
            "SELECT artist, title FROM songs WHERE artist != '' AND title != ''"
        ).fetchall()
    return [f"{r['artist']} - {r['title']}" for r in satirlar]


def db_song_label(song_id: int) -> Optional[str]:
    """Verilen song_id'nin mevcut Spotify etiketini döndürür. Kayıt yoksa None."""
    with _baglanti() as con:
        satir = con.execute("SELECT label FROM songs WHERE id = ?", (song_id,)).fetchone()
    return satir["label"] if satir else None


def db_already_analyzed(song_id: int, analyzer: str) -> bool:
    """Bu şarkı bu analyzer ile daha önce analiz edilmiş mi?"""
    with _baglanti() as con:
        satir = con.execute(
            "SELECT id FROM analyses WHERE song_id = ? AND analyzer = ?",
            (song_id, analyzer)
        ).fetchone()
    return satir is not None


# ── Özet & Sorgular ───────────────────────────────────────────────────────────

def veri_seti_tara(klasor: str = None) -> None:
    """
    veri_seti/ klasöründeki tüm MIDI dosyalarını tarar ve songs tablosuna ekler.
    Spotify etiketi olmadan sadece filename/artist/title/language/midi_path kaydeder.
    Zaten kayıtlı dosyalara dokunmaz.
    """
    import glob
    import re

    if klasor is None:
        klasor = os.path.join(os.path.dirname(__file__), "..", "veri_seti")

    klasor = os.path.abspath(klasor)

    dosyalar = glob.glob(os.path.join(klasor, "**", "*.mid"), recursive=True) + \
               glob.glob(os.path.join(klasor, "**", "*.midi"), recursive=True)
    dosyalar = sorted(set(dosyalar))

    if not dosyalar:
        print(f"[DB] '{klasor}' içinde MIDI dosyası bulunamadı.")
        return

    db_init()
    eklenen = atlanan = 0

    for dosya_yolu in dosyalar:
        dosya_adi = os.path.basename(dosya_yolu)

        # Klasör adından dil tespiti
        klasor_adi = os.path.basename(os.path.dirname(dosya_yolu)).lower()
        if "türkçe" in klasor_adi or "turkce" in klasor_adi:
            dil = "tr"
        elif "yabancı" in klasor_adi or "yabanci" in klasor_adi:
            dil = "en"
        else:
            dil = "unknown"

        # Dosya adından sanatçı ve şarkı ayrıştır
        stem = re.sub(r'_davulsuz.*$', '', os.path.splitext(dosya_adi)[0], flags=re.IGNORECASE).strip()
        parcalar = stem.split('-', 1)
        artist = parcalar[0].strip() if len(parcalar) == 2 else ""
        title  = parcalar[1].strip() if len(parcalar) == 2 else stem

        with _baglanti() as con:
            mevcut = con.execute("SELECT id FROM songs WHERE filename = ?", (dosya_adi,)).fetchone()

        if mevcut:
            atlanan += 1
            continue

        db_get_or_create_song(
            filename=dosya_adi,
            artist=artist,
            title=title,
            language=dil,
            midi_path=dosya_yolu,
        )
        eklenen += 1
        print(f"[DB] Eklendi [{dil.upper()}]: {artist} - {title}")

    print(f"\n[DB] Tarama tamamlandı — Eklenen: {eklenen}, Zaten kayıtlı: {atlanan}")


def db_summary() -> None:
    """Konsola veritabanı özetini basar."""
    with _baglanti() as con:
        toplam_sarki   = con.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
        etiketli       = con.execute("SELECT COUNT(*) FROM songs WHERE label != 'unknown'").fetchone()[0]
        toplam_analiz  = con.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
        dogru_tespit   = con.execute(
            "SELECT ROUND(AVG(key_correct)*100, 1) FROM analyses WHERE key_correct IS NOT NULL"
        ).fetchone()[0]
        tr_sayisi = con.execute("SELECT COUNT(*) FROM songs WHERE language='tr'").fetchone()[0]
        en_sayisi = con.execute("SELECT COUNT(*) FROM songs WHERE language='en'").fetchone()[0]

    print("\n" + "=" * 50)
    print("HarmonAI Veritabanı Özeti")
    print("=" * 50)
    print(f"  Toplam şarkı      : {toplam_sarki}")
    print(f"  Türkçe / Yabancı  : {tr_sayisi} / {en_sayisi}")
    print(f"  Spotify etiketli  : {etiketli}")
    print(f"  Toplam analiz     : {toplam_analiz}")
    if dogru_tespit is not None:
        print(f"  Ton tespit doğrul.: %{dogru_tespit}")
    print("=" * 50)

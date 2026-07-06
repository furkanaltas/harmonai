"""
db_manager.py — HarmonAI PostgreSQL Veritabanı Yöneticisi
==========================================================

Tablo yapısı:
    songs     : Şarkı metadata + Spotify ground truth
    analyses  : Her analiz çalışmasının sonuçları (key_correct dahil)

Kullanım:
    from modules.db_manager import db_get_or_create_song, db_save_analysis, db_summary
"""

import json
import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Bağlantı bilgileri env'den okunur; yoksa yerel geliştirme varsayılanları geçerli.
DB_HOST = os.getenv("HARMONAI_DB_HOST", "localhost")
DB_NAME = os.getenv("HARMONAI_DB_NAME", "harmonai")
DB_USER = os.getenv("HARMONAI_DB_USER", "furkan")
SUPABASE_HOST = os.getenv("SUPABASE_DB_HOST", "db.kjrfyqsqmfljhwraobmw.supabase.co")


# ── Bağlantı ──────────────────────────────────────────────────────────────────

def _baglanti() -> psycopg2.extensions.connection:
    """
    Varsayılan backend YERELdir. Supabase'e bağlanmak için .env'e
    HARMONAI_DB_BACKEND=supabase ekle (supabase_password da tanımlı olmalı).
    Not: db.<ref>.supabase.co doğrudan bağlantısı IPv6 gerektirir; IPv4 ağda
    Session Pooler adresini SUPABASE_DB_HOST olarak vermek gerekir.
    Hiçbir şifre bulunamazsa belirsiz bir psycopg2 hatası yerine açık hata verir.
    """
    backend = os.getenv("HARMONAI_DB_BACKEND", "local").lower()
    supabase_sifre = os.getenv("supabase_password")
    if backend == "supabase" and supabase_sifre:
        con = psycopg2.connect(
            host=SUPABASE_HOST,
            port=5432,
            database="postgres",
            user="postgres",
            password=supabase_sifre,
            sslmode="require"
        )
    else:
        sifre = os.getenv("HARMONAI_DB_PASSWORD") or os.getenv("database_password")
        if not sifre:
            raise RuntimeError(
                "Veritabanı şifresi bulunamadı. .env dosyasında 'database_password' "
                "(yerel PostgreSQL) veya 'supabase_password' (Supabase) tanımlı olmalı."
            )
        con = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=sifre,
        )
    con.autocommit = False
    return con


def _cursor(con):
    return con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def db_init() -> None:
    """Tablolar yoksa oluşturur. Varsa dokunmaz."""
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS songs (
                    id                  SERIAL PRIMARY KEY,
                    filename            TEXT    NOT NULL UNIQUE,
                    artist              TEXT,
                    title               TEXT,
                    language            TEXT    CHECK(language IN ('tr','en','unknown')) DEFAULT 'unknown',
                    midi_path           TEXT,
                    spotify_key         INTEGER,
                    label               TEXT    DEFAULT 'unknown',
                    ground_truth_label  TEXT    DEFAULT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id             SERIAL PRIMARY KEY,
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
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_analyses_song_id ON analyses(song_id)
            """)
    finally:
        con.close()
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
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute("SELECT id FROM songs WHERE filename = %s", (filename,))
            satir = cur.fetchone()

            if satir:
                cur.execute(
                    "UPDATE songs SET midi_path = %s, language = %s WHERE id = %s",
                    (midi_path, language, satir["id"])
                )
                return satir["id"]

            cur.execute(
                """INSERT INTO songs (filename, artist, title, language, midi_path)
                   VALUES (%s, %s, %s, %s, %s)
                   RETURNING id""",
                (filename, artist, title, language, midi_path)
            )
            return cur.fetchone()["id"]
    finally:
        con.close()


def db_update_spotify(
    filename: str,
    spotify_key: Optional[int],
    spotify_mode: Optional[int],  # artık kullanılmıyor, geriye dönük uyumluluk için tutuldu
    label: str,
) -> None:
    """Key ve label ile songs tablosunu günceller."""
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute(
                """UPDATE songs
                   SET spotify_key = %s, label = %s
                   WHERE filename = %s""",
                (spotify_key, label, filename)
            )
    finally:
        con.close()


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

    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute("SELECT spotify_key FROM songs WHERE id = %s", (song_id,))
            spotify_satir = cur.fetchone()

            key_correct = None
            if spotify_satir and spotify_satir["spotify_key"] is not None:
                spotify_nota = NOTE_NAMES[spotify_satir["spotify_key"]]
                key_correct = 1 if spotify_nota == detected_key else 0

            cur.execute(
                """INSERT INTO analyses
                   (song_id, analyzed_at, analyzer, detected_key, detected_mode,
                    tempo, chords, chord_sequence, web_chords, web_source_url, key_correct)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (
                    song_id,
                    datetime.now().isoformat(timespec="seconds"),
                    analyzer,
                    detected_key,
                    detected_mode,
                    round(tempo, 2),
                    json.dumps(chords, ensure_ascii=False),
                    json.dumps(chord_sequence[:500], ensure_ascii=False),
                    json.dumps(web_chords.get("unique_chords", []), ensure_ascii=False),
                    web_chords.get("source_url"),
                    key_correct,
                )
            )
            return cur.fetchone()["id"]
    finally:
        con.close()


def db_song_count() -> int:
    """songs tablosundaki toplam kayıt sayısını döndürür."""
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute("SELECT COUNT(*) AS n FROM songs")
            return cur.fetchone()["n"]
    finally:
        con.close()


def db_song_exists(artist: str, title: str) -> bool:
    """
    Şarkının DB'de kayıtlı olup olmadığını 3 kademede kontrol eder:
      1. Tam eşleşme (artist + title)
      2. ILIKE kısmi eşleşme (büyük/küçük harf duyarsız)
      3. filename içinde geçiyor mu (YouTube başlığıyla kaydedilmiş olabilir)
    dataset_builder'ın mükerrer indirme kontrolü için kullanılır.
    """
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            if artist and title:
                cur.execute(
                    "SELECT id FROM songs WHERE artist = %s AND title = %s LIMIT 1",
                    (artist, title)
                )
                if cur.fetchone():
                    return True
                cur.execute(
                    "SELECT id FROM songs WHERE artist ILIKE %s AND title ILIKE %s LIMIT 1",
                    (f"%{artist}%", f"%{title}%")
                )
                if cur.fetchone():
                    return True
                cur.execute(
                    "SELECT id FROM songs WHERE filename ILIKE %s LIMIT 1",
                    (f"%{title[:30]}%",)
                )
                return cur.fetchone() is not None

            sorgu = title or artist
            if not sorgu:
                return False
            cur.execute(
                "SELECT id FROM songs WHERE title ILIKE %s OR filename ILIKE %s LIMIT 1",
                (f"%{sorgu}%", f"%{sorgu[:30]}%")
            )
            return cur.fetchone() is not None
    finally:
        con.close()


def db_get_existing_songs() -> list[str]:
    """
    DB'deki tüm şarkıları "artist - title" formatında döndürür.
    Gemini prompt'una geçmek için kullanılır (tekrar üretimi önler).
    """
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute("SELECT artist, title FROM songs WHERE artist != '' AND title != ''")
            satirlar = cur.fetchall()
    finally:
        con.close()
    return [f"{r['artist']} - {r['title']}" for r in satirlar]


def db_song_label(song_id: int) -> Optional[str]:
    """Verilen song_id'nin mevcut Spotify etiketini döndürür. Kayıt yoksa None."""
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute("SELECT label FROM songs WHERE id = %s", (song_id,))
            satir = cur.fetchone()
    finally:
        con.close()
    return satir["label"] if satir else None


def db_random_sample_for_ground_truth(n: int = 40) -> list[dict]:
    """
    Henüz insan tarafından doğrulanmamış (ground_truth_label IS NULL),
    sistem tarafından etiketlenmiş n adet rastgele şarkı döndürür.
    """
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute(
                """SELECT id, filename, artist, title, midi_path
                   FROM songs
                   WHERE label != 'unknown' AND ground_truth_label IS NULL
                   ORDER BY RANDOM()
                   LIMIT %s""",
                (n,)
            )
            return cur.fetchall()
    finally:
        con.close()


def db_set_ground_truth(song_id: int, ground_truth_label: str) -> None:
    """İnsan tarafından doğrulanmış (kulakla belirlenmiş) etiketi kaydeder."""
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute(
                "UPDATE songs SET ground_truth_label = %s WHERE id = %s",
                (ground_truth_label, song_id)
            )
    finally:
        con.close()


def db_ground_truth_rows() -> list[dict]:
    """İnsan doğrulamalı tüm satırları döndürür (confusion matrix raporu için)."""
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute(
                """SELECT artist, title, label, ground_truth_label
                   FROM songs
                   WHERE ground_truth_label IS NOT NULL"""
            )
            return cur.fetchall()
    finally:
        con.close()


def db_ground_truth_accuracy() -> dict:
    """
    İnsan tarafından doğrulanmış şarkılarda sistem tahmini (label) ile
    insan etiketini (ground_truth_label) karşılaştırıp doğruluk raporu üretir.
    """
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute(
                """SELECT filename, artist, title, label, ground_truth_label
                   FROM songs
                   WHERE ground_truth_label IS NOT NULL"""
            )
            satirlar = cur.fetchall()
    finally:
        con.close()

    toplam = len(satirlar)
    dogru = sum(1 for r in satirlar if r["label"] == r["ground_truth_label"])
    yanlislar = [r for r in satirlar if r["label"] != r["ground_truth_label"]]

    return {
        "toplam": toplam,
        "dogru": dogru,
        "oran": round(dogru / toplam * 100, 1) if toplam else None,
        "yanlislar": yanlislar,
    }


def db_already_analyzed(song_id: int, analyzer: str) -> bool:
    """Bu şarkı bu analyzer ile daha önce analiz edilmiş mi?"""
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute(
                "SELECT id FROM analyses WHERE song_id = %s AND analyzer = %s",
                (song_id, analyzer)
            )
            return cur.fetchone() is not None
    finally:
        con.close()


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

        klasor_adi = os.path.basename(os.path.dirname(dosya_yolu)).lower()
        if "türkçe" in klasor_adi or "turkce" in klasor_adi:
            dil = "tr"
        elif "yabancı" in klasor_adi or "yabanci" in klasor_adi:
            dil = "en"
        else:
            dil = "unknown"

        stem = re.sub(r'_davulsuz.*$', '', os.path.splitext(dosya_adi)[0], flags=re.IGNORECASE).strip()
        parcalar = stem.split('-', 1)
        artist = parcalar[0].strip() if len(parcalar) == 2 else ""
        title  = parcalar[1].strip() if len(parcalar) == 2 else stem

        con = _baglanti()
        try:
            with con:
                cur = _cursor(con)
                cur.execute("SELECT id FROM songs WHERE filename = %s", (dosya_adi,))
                mevcut = cur.fetchone()
        finally:
            con.close()

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
    con = _baglanti()
    try:
        with con:
            cur = _cursor(con)
            cur.execute("SELECT COUNT(*) AS n FROM songs")
            toplam_sarki = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) AS n FROM songs WHERE label != 'unknown'")
            etiketli = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) AS n FROM analyses")
            toplam_analiz = cur.fetchone()["n"]

            cur.execute(
                "SELECT ROUND(AVG(key_correct::numeric)*100, 1) AS ort FROM analyses WHERE key_correct IS NOT NULL"
            )
            dogru_tespit = cur.fetchone()["ort"]

            cur.execute("SELECT COUNT(*) AS n FROM songs WHERE language='tr'")
            tr_sayisi = cur.fetchone()["n"]

            cur.execute("SELECT COUNT(*) AS n FROM songs WHERE language='en'")
            en_sayisi = cur.fetchone()["n"]
    finally:
        con.close()

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

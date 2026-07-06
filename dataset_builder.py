"""
dataset_builder.py — HarmonAI Toplu Veri Seti Oluşturucu
=========================================================

PIPELINE AKIŞI (her şarkı için):
    1. Groq (llama-3.3-70b) ile Türkçe + Batı şarkı listesi üret (dinamik)
    2. Her şarkı için YouTube'da ytsearch1 ile ilk videoyu bul
    3. Sesi WAV olarak geçici klasöre indir
    4. Basic Pitch (CNN) ile MIDI'ye çevir
    5. Davulları temizle (audio_core.clean_midi_drums)
    6. Dile göre doğru klasöre kaydet (Türkçe / Yabancı)
    7. Geçici WAV ve ham MIDI'yi sil

KULLANIM:
    python dataset_builder.py                        # 50 şarkı (25 TR + 25 EN)
    python dataset_builder.py --adet 100             # 100 şarkı (50/50)
    python dataset_builder.py --adet 10 --test       # Test: sadece 5 TR + 5 EN
    python dataset_builder.py --tr 30 --en 20        # Özel oran
"""

import os
import re
import sys
import glob
import time
import random
import shutil
import logging
import argparse
import contextlib
import io
from pathlib import Path
from typing import Optional

# ── Ortam değişkenleri (TF gürültüsünü sustur) ──────────────────────────────
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS', '0')

import warnings
warnings.filterwarnings('ignore')

# ── Logger (tüm modülde kullanılacak, import'lardan ÖNCE tanımlanmalı) ───────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger('dataset_builder')

# ── Dış kütüphaneler ─────────────────────────────────────────────────────────
import socket
from dotenv import load_dotenv
from groq import Groq
from yt_dlp import YoutubeDL

with contextlib.redirect_stderr(io.StringIO()):
    from basic_pitch.inference import predict_and_save
    from basic_pitch import ICASSP_2022_MODEL_PATH

from modules.audio_core import clean_midi_drums
from modules.db_manager import db_init, db_get_or_create_song, db_get_existing_songs, db_song_exists

# ── Yapılandırma ──────────────────────────────────────────────────────────────
load_dotenv()

TURKCE_CIKTI_KLASORU: str = r"C:\Users\Asus\Desktop\HarmonAI\veri_seti\Midi Çıktıları\Türkçe"
BATI_CIKTI_KLASORU:   str = r"C:\Users\Asus\Desktop\HarmonAI\veri_seti\Midi Çıktıları\Yabancı"
GECICI_INDIRME_KLASORU: str = r"C:\Users\Asus\Desktop\HarmonAI\dataset_temp_audio"

# Her şarkı için YouTube'da kaç sonuç taranır (ilk uygun olan alınır)
YOUTUBE_ARAMA_DERINLIGI: int = 3

# Süre filtresi (saniye)
MIN_SURE_SN: int = 90   # 1:30
MAX_SURE_SN: int = 480  # 8:00

_GROQ_HOST = "api.groq.com"
# Şarkı listesi üretimi için Groq (llama-3.3-70b) kullanılır.
# Groq ücretsiz tier: 14.400 req/gün, ~500 token/sn — Gemini'den çok daha hızlı.
_GROQ_MODEL = "llama-3.3-70b-versatile"


def _groq_client() -> Groq | None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        log.error("GROQ_API_KEY bulunamadı. .env dosyasını kontrol et.")
        return None
    try:
        return Groq(api_key=api_key)
    except Exception as e:
        log.error(f"Groq istemcisi başlatılamadı: {e}")
        return None


def _check_connectivity() -> bool:
    try:
        with socket.create_connection((_GROQ_HOST, 443), timeout=5):
            return True
    except Exception:
        return False


# ── AI Şarkı Listesi Üretimi ──────────────────────────────────────────────────

def ai_sarki_listesi_olustur(tr_adet: int, en_adet: int) -> list[tuple[str, str]]:
    """
    Groq (llama-3.3-70b) üzerinden Türkçe ve Batı şarkıları ister.
    DB'deki mevcut sanatçıları prompt'a ekleyerek tekrar üretimi önler.

    Döndürür:
        [(sarki_adi, dil), ...] — dil: "tr" veya "en"
        Hata durumunda boş liste.
    """
    if not _check_connectivity():
        log.error("Groq API'ye erişilemiyor. İnternet bağlantısını kontrol et.")
        return []

    client = _groq_client()
    if not client:
        return []

    # DB'deki mevcut şarkıları çek — rastgele 80 örnek gönder
    # Rastgele örnekleme: her batch'te farklı şarkılar referans alınır,
    # böylece Groq aynı 80 şarkı etrafında döngüye girmez.
    mevcut_sarkilar = db_get_existing_songs()
    mevcut_blok = ""
    if mevcut_sarkilar:
        orneklem = random.sample(mevcut_sarkilar, min(80, len(mevcut_sarkilar)))
        liste_metni = "\n".join(f"- {s}" for s in orneklem)
        mevcut_blok = f"""
ZATEN MEVCUT ŞARKILAR (bunları tekrar önerme, benzerlerini de önerme):
{liste_metni}

"""
        log.info(f"Groq'a {len(orneklem)}/{len(mevcut_sarkilar)} rastgele şarkı gönderiliyor.")

    prompt = f"""You are a music dataset assistant. Generate a song list for a harmonic analysis dataset.{mevcut_blok}
Generate exactly {tr_adet} Turkish songs and {en_adet} Western/English songs.
Requirements:
- Real instruments (no electronic/techno/trap/EDM)
- Clear chord structure (pop, rock, folk, classical pop)
- Diverse artists and eras (1970s to 2020s)
- No duplicates from the existing list above

Output ONLY in this exact format, nothing else:
TR|Artist - Song Title
EN|Artist - Song Title
"""

    for deneme in range(1, 4):
        try:
            log.info(f"Groq'tan şarkı listesi isteniyor (deneme {deneme}/3)...")
            response = client.chat.completions.create(
                model=_GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.9,   # yüksek yaratıcılık → farklı şarkılar
                max_tokens=1024,
                timeout=20,
            )
            metin = response.choices[0].message.content.strip()
            satirlar = metin.split("\n")
            sonuc: list[tuple[str, str]] = []

            for satir in satirlar:
                satir = satir.strip()
                if satir.startswith("TR|"):
                    sonuc.append((satir[3:].strip(), "tr"))
                elif satir.startswith("EN|"):
                    sonuc.append((satir[3:].strip(), "en"))

            if sonuc:
                log.info(f"Groq {len(sonuc)} şarkı döndürdü "
                         f"({sum(1 for _, d in sonuc if d=='tr')} TR, "
                         f"{sum(1 for _, d in sonuc if d=='en')} EN).")
                return sonuc
            else:
                log.warning("Groq yanıtı ayrıştırılamadı, tekrar deneniyor...")
                time.sleep(2)

        except Exception as e:
            log.error(f"Groq hatası (deneme {deneme}): {e}")
            time.sleep(3)

    log.error("Groq'tan şarkı listesi alınamadı.")
    return []


# ── YouTube Arama & İndirme ───────────────────────────────────────────────────

def _youtube_ara(sarki_adi: str) -> Optional[tuple[str, str, int]]:
    """
    Şarkı adıyla YouTube'da arama yapar, süre filtresine uyan ilk videoyu döndürür.

    Döndürür:
        (video_url, video_baslik, sure_sn) veya None
    """
    arama_sorgusu = f"ytsearch{YOUTUBE_ARAMA_DERINLIGI}:{sarki_adi} official audio"
    opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True, 'skip_download': True}

    try:
        with YoutubeDL(opts) as ydl:
            sonuc = ydl.extract_info(arama_sorgusu, download=False)
        videolar = sonuc.get('entries', [])
    except Exception as e:
        log.error(f"YouTube arama hatası [{sarki_adi}]: {e}")
        return None

    for video in videolar:
        if not video:
            continue
        sure = int(video.get('duration') or 0)
        if MIN_SURE_SN <= sure <= MAX_SURE_SN:
            url = f"https://www.youtube.com/watch?v={video['id']}"
            return url, video.get('title', sarki_adi), sure

    log.warning(f"Süre filtresine uyan video bulunamadı: {sarki_adi}")
    return None


def _guvenli_dosya_adi(metin: str, max_uzunluk: int = 80) -> str:
    """Dosya adında sorun çıkarabilecek karakterleri temizler."""
    temiz = re.sub(r'[^\w\s\-_()]', '', metin, flags=re.UNICODE)
    return temiz.strip()[:max_uzunluk] or "bilinmeyen_sarki"


def _ses_indir(video_url: str, baslik: str) -> Optional[str]:
    """YouTube URL'sinden WAV indirir. Daha önce indirilmişse atlar."""
    guvenli_ad = _guvenli_dosya_adi(baslik)
    hedef_yol = os.path.join(GECICI_INDIRME_KLASORU, guvenli_ad)

    mevcut = glob.glob(f"{hedef_yol}*.wav")
    if mevcut:
        log.info(f"   ♻️  Zaten indirilmiş, atlanıyor.")
        return mevcut[0]

    opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav', 'preferredquality': '192'}],
        'outtmpl': f"{hedef_yol}.%(ext)s",
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([video_url])
        bulunan = glob.glob(f"{hedef_yol}*.wav")
        return bulunan[0] if bulunan else None
    except Exception as e:
        log.error(f"   İndirme hatası: {e}")
        return None


# ── MIDI Dönüşümü ─────────────────────────────────────────────────────────────

def _wav_to_midi(wav_yolu: str) -> Optional[str]:
    """WAV → Basic Pitch MIDI. Daha önce dönüştürülmüşse atlar."""
    klasor = os.path.dirname(wav_yolu)
    temel_ad = os.path.splitext(os.path.basename(wav_yolu))[0]

    # Basic Pitch çıktı adı deterministiktir: <girdi_adı>_basic_pitch.mid
    # Eşzamanlı çalışmada (auto_builder + app) getctime'a göre "en yeni .mid"
    # seçmek yanlış dosyayı yakalayabilir; önce beklenen adı doğrudan kontrol et.
    beklenen = os.path.join(klasor, f"{temel_ad}_basic_pitch.mid")
    if os.path.exists(beklenen):
        log.info("   ♻️  MIDI zaten mevcut.")
        return beklenen

    try:
        with contextlib.redirect_stderr(io.StringIO()):
            predict_and_save(
                [wav_yolu],
                output_directory=klasor,
                save_midi=True,
                sonify_midi=False,
                save_model_outputs=False,
                save_notes=False,
                model_or_model_path=ICASSP_2022_MODEL_PATH,
            )
    except Exception as e:
        if "already exists" in str(e):
            if os.path.exists(beklenen):
                return beklenen
            adaylar = glob.glob(os.path.join(klasor, f"*{temel_ad}*.mid"))
            return max(adaylar, key=os.path.getctime) if adaylar else None
        log.error(f"   Basic Pitch hatası: {e}")
        return None

    if os.path.exists(beklenen):
        return beklenen
    adaylar = glob.glob(os.path.join(klasor, f"*{temel_ad}*.mid"))
    return max(adaylar, key=os.path.getctime) if adaylar else None


def _midi_kaydet(midi_yolu: str, hedef_klasor: str, sarki_adi: str) -> Optional[str]:
    """
    Davulsuz MIDI'yi hedef klasöre kopyalar.
    Başarılı olursa hedef dosya yolunu, hata durumunda None döner.
    """
    guvenli_ad = _guvenli_dosya_adi(sarki_adi)
    hedef = os.path.join(hedef_klasor, f"{guvenli_ad}_davulsuz.mid")

    sayac = 2
    while os.path.exists(hedef):
        hedef = os.path.join(hedef_klasor, f"{guvenli_ad}_davulsuz_{sayac}.mid")
        sayac += 1

    try:
        shutil.copy2(midi_yolu, hedef)
        log.info(f"   Kaydedildi: {os.path.basename(hedef)}")
        return hedef
    except Exception as e:
        log.error(f"   Kaydetme hatası: {e}")
        return None


def _temizle(*dosyalar: Optional[str]) -> None:
    """Geçici dosyaları diskten siler."""
    for dosya in dosyalar:
        if dosya and os.path.exists(dosya):
            try:
                os.remove(dosya)
            except Exception as e:
                log.warning(f"   Silinemedi [{dosya}]: {e}")


# ── Tek Şarkı Pipeline ────────────────────────────────────────────────────────

def _db_de_var_mi(sarki_adi: str) -> bool:
    """
    Şarkı adı DB'de (PostgreSQL) zaten kayıtlıysa True döner.
    Kontrol db_manager.db_song_exists ile 3 kademede yapılır (tam → ILIKE → filename).
    Bu sayede "Duman - Herşey Seninle Güzel" sorgusu,
    "Duman - Herşey Seninle Güzel (Official Audio)" girişlerini de yakalar.
    """
    parca = sarki_adi.split('-', 1)
    if len(parca) == 2:
        artist, title = parca[0].strip(), parca[1].strip()
    else:
        artist, title = "", sarki_adi.strip()
    try:
        return db_song_exists(artist, title)
    except Exception as e:
        log.warning(f"   DB duplicate kontrolü başarısız ({type(e).__name__}): {e}")
        return False


def _tek_sarki_isle(sarki_adi: str, dil: str) -> bool:
    """
    Tek şarkı için: DB Kontrol → YouTube Ara → İndir → MIDI → Davul Temizle → Kaydet → Temizle
    Hata tek şarkıyı durdurur, batch'e dokunmaz.
    """
    hedef_klasor = TURKCE_CIKTI_KLASORU if dil == "tr" else BATI_CIKTI_KLASORU
    wav_yolu: Optional[str] = None
    ham_midi: Optional[str] = None

    try:
        # 0. DB'de zaten var mı?
        if _db_de_var_mi(sarki_adi):
            log.info(f"   ♻️  DB'de zaten mevcut, atlanıyor: {sarki_adi}")
            return "zaten_var"

        # 1. YouTube'da ara
        arama_sonucu = _youtube_ara(sarki_adi)
        if not arama_sonucu:
            return False
        video_url, video_baslik, sure = arama_sonucu
        log.info(f"   Bulundu: {video_baslik[:60]} ({sure//60}:{sure%60:02d})")

        # 2. İndir
        wav_yolu = _ses_indir(video_url, video_baslik)
        if not wav_yolu:
            return False

        # 3. WAV → MIDI
        ham_midi = _wav_to_midi(wav_yolu)
        if not ham_midi:
            return False

        # 4. Davulları temizle
        davulsuz = clean_midi_drums(ham_midi)
        if not davulsuz:
            log.error("   Davul temizleme başarısız.")
            return False

        # 5. Hedef klasöre kaydet
        hedef_midi_yolu = _midi_kaydet(davulsuz, hedef_klasor, video_baslik)
        if not hedef_midi_yolu:
            return False

        # 6. DB'ye kaydet
        stem = re.sub(r'_davulsuz.*$', '', os.path.splitext(os.path.basename(hedef_midi_yolu))[0], flags=re.IGNORECASE)
        parcalar = stem.split('-', 1)
        artist = parcalar[0].strip() if len(parcalar) == 2 else sarki_adi
        title  = parcalar[1].strip() if len(parcalar) == 2 else video_baslik
        db_get_or_create_song(
            filename=os.path.basename(hedef_midi_yolu),
            artist=artist,
            title=title,
            language=dil,
            midi_path=hedef_midi_yolu,
        )

        # 7. Geçici dosyaları sil
        _temizle(wav_yolu, ham_midi)
        if os.path.normpath(os.path.dirname(davulsuz)) != os.path.normpath(hedef_klasor):
            _temizle(davulsuz)

        return True

    except Exception as e:
        log.exception(f"   Beklenmeyen hata [{sarki_adi}]: {e}")
        _temizle(wav_yolu, ham_midi)
        return False


# ── Ana Batch Pipeline ────────────────────────────────────────────────────────

def veri_seti_olustur(tr_adet: int = 25, en_adet: int = 25) -> None:
    """
    Groq'tan şarkı listesi al ve her biri için pipeline'ı çalıştır.

    Parametreler:
        tr_adet : İstenilen Türkçe şarkı sayısı
        en_adet : İstenilen Batı/Yabancı şarkı sayısı
    """
    for klasor in [TURKCE_CIKTI_KLASORU, BATI_CIKTI_KLASORU, GECICI_INDIRME_KLASORU]:
        Path(klasor).mkdir(parents=True, exist_ok=True)
    db_init()

    log.info("=" * 65)
    log.info("HarmonAI Veri Seti Oluşturucu Başlatıldı")
    log.info(f"Hedef: {tr_adet} Türkçe + {en_adet} Batı = {tr_adet + en_adet} şarkı")
    log.info("=" * 65)

    sarki_listesi = ai_sarki_listesi_olustur(tr_adet, en_adet)
    if not sarki_listesi:
        log.error("Şarkı listesi alınamadı, işlem iptal.")
        return

    toplam = len(sarki_listesi)
    basarili = atlanan = zaten_var = 0

    for idx, (sarki_adi, dil) in enumerate(sarki_listesi, start=1):
        dil_etiketi = "TR" if dil == "tr" else "EN"
        log.info(f"\n[{idx}/{toplam}] [{dil_etiketi}] {sarki_adi}")

        sonuc = _tek_sarki_isle(sarki_adi, dil)

        if sonuc == "zaten_var":
            zaten_var += 1
        elif sonuc:
            basarili += 1
            log.info(f"   ✅ Başarılı! (Yeni: {basarili}/{toplam})")
        else:
            atlanan += 1
            log.info("   ⚠️  Atlandı.")

        time.sleep(1.5)  # YouTube rate limit için bekleme

    log.info("\n" + "=" * 65)
    log.info("BATCH TAMAMLANDI")
    log.info(f"  Yeni eklenen  : {basarili}")
    log.info(f"  Zaten vardı   : {zaten_var}")
    log.info(f"  Atlanan/Hata  : {atlanan}")
    log.info(f"  Türkçe klasör : {TURKCE_CIKTI_KLASORU}")
    log.info(f"  Batı klasörü  : {BATI_CIKTI_KLASORU}")
    log.info("=" * 65)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="HarmonAI Toplu Veri Seti Oluşturucu",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python dataset_builder.py                  # 25 TR + 25 EN (varsayılan)
  python dataset_builder.py --tr 40 --en 10  # 40 Türkçe + 10 Batı
  python dataset_builder.py --tr 5 --en 5 --test
        """
    )
    parser.add_argument('--tr',   type=int, default=25, help='Türkçe şarkı sayısı (varsayılan: 25)')
    parser.add_argument('--en',   type=int, default=25, help='Batı şarkı sayısı (varsayılan: 25)')
    parser.add_argument('--test', action='store_true',  help='Test modu: --tr ve --en değerlerini 3 ile sınırlar')

    args = parser.parse_args()

    if args.test:
        log.info("TEST MODU: her dilden en fazla 3 şarkı.")
        veri_seti_olustur(tr_adet=min(args.tr, 3), en_adet=min(args.en, 3))
    else:
        veri_seti_olustur(tr_adet=args.tr, en_adet=args.en)

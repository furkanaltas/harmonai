"""
auto_builder.py — HarmonAI Otomatik Dataset Oluşturucu
=======================================================

AMAÇ:
    dataset_builder.py'yi arka planda periyodik olarak çalıştırır.
    Hedef şarkı sayısına ulaşılana kadar her çalışmada küçük bir batch indirir.
    YouTube rate limit'ini ve disk alanını gözeterek akıllıca durur.

ÇALIŞMA MANTIĞI:
    1. DB'de kaç şarkı var? → Hedefin altındaysa batch başlat
    2. Her batch'te TR_BATCH_ADET TR + EN_BATCH_ADET EN şarkı indir
    3. BEKLEME_SAAT saat bekle → tekrar kontrol et
    4. HEDEF_SARKI_SAYISI'na ulaşınca dur

KULLANIM:
    python auto_builder.py                    # Varsayılan ayarlarla başlat
    python auto_builder.py --hedef 200        # 200 şarkıya kadar çalış
    python auto_builder.py --bekle 6          # 6 saatte bir çalış
    python auto_builder.py --simdi            # Beklemeden hemen bir kez çalıştır

ARKA PLANDA ÇALIŞTIRMAK (Windows):
    start /min python auto_builder.py         # Küçültülmüş terminalde
    pythonw auto_builder.py                   # Konsol penceresi olmadan (sessiz)
"""

import argparse
import logging
import sqlite3
import sys
import time
import os

import schedule

# modules/ klasöründen çalıştırıldığında proje kökünü path'e ekle
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Logger ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(_ROOT, "auto_builder.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger("auto_builder")

# ── Varsayılan Ayarlar ────────────────────────────────────────────────────────

HEDEF_SARKI_SAYISI: int = 2000  # Toplam hedef (TR + EN)
TR_BATCH_ADET:     int = 8      # Her çalışmada indirilecek TR şarkı sayısı
EN_BATCH_ADET:     int = 7      # Her çalışmada indirilecek EN şarkı sayısı
BEKLEME_SAAT:      float = 1  # Çalışmalar arası bekleme süresi (saat)

MIN_DISK_GB:       float = 2.0  # Minimum boş disk alanı (GB) — altındaysa dur
DB_YOLU:           str = os.path.join(_ROOT, "dataset.db")


# ── Kontroller ────────────────────────────────────────────────────────────────

def _mevcut_sarki_sayisi() -> int:
    """DB'deki toplam şarkı sayısını döndürür. DB yoksa 0."""
    if not os.path.exists(DB_YOLU):
        return 0
    try:
        with sqlite3.connect(DB_YOLU) as con:
            return con.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
    except Exception:
        return 0


def _bos_disk_gb() -> float:
    """Proje diskindeki boş alanı GB cinsinden döndürür."""
    import shutil
    toplam, kullanilan, bos = shutil.disk_usage(os.path.dirname(__file__))
    return bos / (1024 ** 3)


def _hedef_tamam(hedef: int) -> bool:
    mevcut = _mevcut_sarki_sayisi()
    if mevcut >= hedef:
        log.info(f"Hedef şarkı sayısına ulaşıldı: {mevcut}/{hedef}. Otomasyon durdu.")
        return True
    return False


def _disk_yeterli() -> bool:
    bos = _bos_disk_gb()
    if bos < MIN_DISK_GB:
        log.warning(f"Disk alanı yetersiz: {bos:.1f}GB boş (minimum {MIN_DISK_GB}GB gerekli). Batch atlandı.")
        return False
    return True


# ── Batch Çalıştırıcı ─────────────────────────────────────────────────────────

def batch_calistir(hedef: int, tr_adet: int, en_adet: int) -> None:
    """
    Tek bir batch çalıştırır:
    - Hedef dolmuşsa veya disk yetersizse çıkar
    - dataset_builder.veri_seti_olustur() çağırır
    """
    mevcut = _mevcut_sarki_sayisi()
    log.info(f"{'='*55}")
    log.info(f"Batch Başlıyor — Mevcut: {mevcut} / Hedef: {hedef}")
    log.info(f"{'='*55}")

    if _hedef_tamam(hedef):
        return

    if not _disk_yeterli():
        return

    # Hedefe kalan kadar indir, batch'ten fazlasını isteme
    kalan = hedef - mevcut
    gercek_tr = min(tr_adet, max(1, kalan // 2))
    gercek_en = min(en_adet, kalan - gercek_tr)

    if gercek_tr + gercek_en <= 0:
        log.info("İndirilecek şarkı kalmadı.")
        return

    log.info(f"Bu batch: {gercek_tr} TR + {gercek_en} EN = {gercek_tr + gercek_en} şarkı")

    try:
        from dataset_builder import veri_seti_olustur
        veri_seti_olustur(tr_adet=gercek_tr, en_adet=gercek_en)
    except Exception as e:
        log.error(f"Batch hatası: {e}")
        return

    yeni_mevcut = _mevcut_sarki_sayisi()
    log.info(f"Batch tamamlandı. DB durumu: {yeni_mevcut}/{hedef} şarkı.")


# ── Zamanlayıcı ───────────────────────────────────────────────────────────────

def otomasyon_baslat(
    hedef:      int   = HEDEF_SARKI_SAYISI,
    tr_adet:    int   = TR_BATCH_ADET,
    en_adet:    int   = EN_BATCH_ADET,
    bekle_saat: float = BEKLEME_SAAT,
    simdi:      bool  = False,
) -> None:
    """
    Zamanlayıcıyı başlatır. bekle_saat saatte bir batch çalıştırır.

    simdi=True ise ilk batch'i bekleme olmadan hemen çalıştırır.
    """
    log.info("=" * 55)
    log.info("HarmonAI Otomatik Dataset Oluşturucu Başlatıldı")
    log.info(f"  Hedef şarkı    : {hedef}")
    log.info(f"  Batch boyutu   : {tr_adet} TR + {en_adet} EN")
    log.info(f"  Çalışma sıklığı: {bekle_saat} saatte bir")
    log.info(f"  Min. disk alanı: {MIN_DISK_GB} GB")
    log.info("=" * 55)

    def _batch():
        if _hedef_tamam(hedef):
            # Hedef doldu — zamanlayıcıyı durdur
            return schedule.CancelJob
        batch_calistir(hedef, tr_adet, en_adet)

    # İlk çalışma
    if simdi:
        log.info("İlk batch hemen başlatılıyor (--simdi)...")
        _batch()

    # Periyodik zamanlama
    schedule.every(bekle_saat).hours.do(_batch)
    log.info(f"Zamanlayıcı kuruldu. İlk otomatik çalışma: {bekle_saat} saat sonra.")
    log.info("Durdurmak için Ctrl+C.")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Her dakika kontrol et
    except KeyboardInterrupt:
        log.info("Otomasyon kullanıcı tarafından durduruldu.")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="HarmonAI Otomatik Dataset Oluşturucu",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  python auto_builder.py                        # Varsayılan: 300 hedef, 4 saatte bir
  python auto_builder.py --hedef 500 --bekle 6  # 500 şarkı, 6 saatte bir
  python auto_builder.py --simdi                # Hemen bir batch başlat, sonra zamanla
  python auto_builder.py --tr 5 --en 5 --simdi # Test: küçük batch, hemen çalıştır

Arka planda çalıştırmak (Windows):
  start /min python auto_builder.py            # Küçültülmüş pencerede
  pythonw auto_builder.py                      # Sessiz (konsol yok) — log dosyasına yazar
        """
    )
    parser.add_argument("--hedef",  type=int,   default=HEDEF_SARKI_SAYISI, help=f"Hedef şarkı sayısı (varsayılan: {HEDEF_SARKI_SAYISI})")
    parser.add_argument("--tr",     type=int,   default=TR_BATCH_ADET,      help=f"Batch başına TR şarkı (varsayılan: {TR_BATCH_ADET})")
    parser.add_argument("--en",     type=int,   default=EN_BATCH_ADET,      help=f"Batch başına EN şarkı (varsayılan: {EN_BATCH_ADET})")
    parser.add_argument("--bekle",  type=float, default=BEKLEME_SAAT,       help=f"Çalışmalar arası bekleme saati (varsayılan: {BEKLEME_SAAT})")
    parser.add_argument("--simdi",  action="store_true",                    help="İlk batch'i hemen çalıştır, beklemeden başla")

    args = parser.parse_args()

    otomasyon_baslat(
        hedef=args.hedef,
        tr_adet=args.tr,
        en_adet=args.en,
        bekle_saat=args.bekle,
        simdi=args.simdi,
    )

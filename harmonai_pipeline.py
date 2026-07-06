# HarmonAI Pipeline ASENKRON VERSIYON

#   AKIŞ (Paralel):
#       [Indir] -> [Web Scraping] --+
#                  [MIDI Donusum] --+--> [Analiz] -> [LLM]

# Neden asyncio?
#   - Web scraping (Selenium/requests) ve Basic Pitch/librosa senkron/bloklayici
#     kutuphaneler oldugundan her biri asyncio.to_thread() ile ayri thread'e
#     devredilir; event loop bloklanmaz.
#   - Iki is asyncio.gather() ile paralel calistirilir; toplam sure en uzun
#     islem kadardir (onceki ThreadPoolExecutor tasarimiyla ayni kazanc).

import asyncio
import time
import pretty_midi
import collections
import os
import sys

# Windows terminali cp1254 kullanır; Gemini raporundaki Unicode semboller patlatır.
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
from modules import llm_agent
from modules import web_scraper
from modules import math_theory
from modules.audio_core import get_accurate_tempo
from modules import audio_core
from modules import fast_analyzer
from modules.db_manager import db_init, db_get_or_create_song, db_save_analysis


def _midi_donusum_pipeline(wav_path: str, output_folder: str):
    """
    Yardımcı iş fonksiyon: MIDI dönüşüm + davul temizleme adımlarını sıralı çalıştırılır ve temizlenmiş MIDI yolunu döndürür.
    ThreadPoolExecutor'a submit edilerek web scraping ile EŞ ZAMANLI çalıştırılmak üzere tasarlanmıştır.
    
    Parametreler:
    wav_path      : Islenecek WAV dosyasinin yolu
    output_folder : MIDI ciktilarinin kaydedilecegi klasor
    Dondurur: Davulsuz MIDI dosyasinin yolu; hata durumunda None
    """

    # Adim A: WAV -> MIDI donusumu (Basic Pitch CNN inference)
    # Hiz: interaktif analizde ilk 120 sn yeterli — ton/akor yapisi bu pencerede
    # oturur; dataset_builder tam sarkiyi kullanmaya devam eder.
    raw_midi = audio_core.audio_to_midi(wav_path, output_folder, max_sure_sn=120)
    if not raw_midi:
        return None

    # Adim B: MIDI'den davul/perkusyon kanallarini temizle
    return audio_core.clean_midi_drums(raw_midi)


async def run_harmonai_pipeline_async(url_or_path: str, artist_name: str, song_title: str):
    """
    Parametreler:
    url_or_path : YouTube linki veya lokal WAV dosya yolu
    artist_name  : Sanatçı adı (web scraping için)
    song_title   : Şarkı adı (web scraping için)

    HarmonAI ana pipeline'inin asenkron/eşzamanlı versiyonu.
    PARALEL ÇALIŞAN BÖLÜMLER:
        Thread-1: web_scraper.scrape_chords_from_web()
                -> I/O bound, Selenium/requests ile ağ bekleniyor
        Thread-2: audio_to_midi() + clean_midi_drums()
                -> CPU bound, ancak TensorFlow GIL'i serbest bırakır
    
    Bu yapı sayesinde toplam süre, iki işlemden uzun olanınki kadardır. Tipik kazanc: ~40-60 sn.
    """

    print('=' * 70)
    print(f'HarmonAI (ASYNC) Başlatılıyor: {artist_name} - {song_title}')
    print('=' * 70)

    output_folder = 'analyzed_songs'
    os.makedirs(output_folder, exist_ok=True)

    # ADIM 1: Ses Dosyasını Hazırla 
    # YouTube indirme veya yerel dosya doğrulaması burada yapılır. Bu adım bitmeden paralel blok başlatılamaz.

    wav_path = None
    if url_or_path.startswith(('http://', 'https://')):
        wav_path, _ = audio_core.process_youtube_link(url_or_path, output_folder)
    else:
        if os.path.exists(url_or_path):
            wav_path = url_or_path
        else:
            print('[HATA] Dosya bulunamadı.')
            return {"error": f"Dosya bulunamadı: {url_or_path}"}

    if not wav_path:
        print('[HATA] Ses dosyası hazırlanamadı, işlem iptal.')
        return {
            "error": (
                "YouTube'dan ses indirilemedi.\n\n"
                "Olası sebepler:\n"
                "• Arka planda auto_builder çalışıyorsa YouTube rate-limit uygular — durdurup tekrar dene\n"
                "• Video bölge kısıtlamalı veya kaldırılmış\n"
                "• YouTube bot koruması tetiklendi — birkaç dakika bekle veya VPN aç"
            )
        }

    # ADIM 2 ve 3: PARALEL CALISMA BLOGU 
    # ThreadPoolExecutor(max_workers=2) ile iki bağımsız görev aynı anda başlatılır. Her biri ayrı bir thread'de yurutulur:
    #   web_gelecek  -> scrape_chords_from_web() sonucunu tutan Future
    #   midi_gelecek -> _midi_donusum_pipeline() sonucunu tutan Future
    # İki .result() cağrısı, ilgili thread tamamlanana kadar bekler. Hangisi önce biterse diğeri devam ederken o sonucu hemen döndürür.

    print('\n Paralel işlemler başlatılıyor (2 iş parçacığı):')
    print('   -> [Thread 1] Web İstihbarati (I/O Bound)  : scrape_chords_from_web()')
    print('   -> [Thread 2] MIDI DÖnüşümü  (CPU Bound)   : audio_to_midi() + clean_midi_drums()')
    print('-' * 70)

    t_baslangic = time.perf_counter()

    # Web scraping (Selenium/requests) ve MIDI pipeline (Basic Pitch) ikisi de
    # senkron/bloklayici oldugundan asyncio.to_thread ile ayri thread'lere
    # devredilir; asyncio.gather ikisini paralel calistirir.
    web_chords, clean_midi = await asyncio.gather(
        asyncio.to_thread(web_scraper.scrape_chords_from_web, artist_name, song_title),
        asyncio.to_thread(_midi_donusum_pipeline, wav_path, output_folder),
    )

    t_bitis = time.perf_counter()
    print(f'\n Her iki paralel işlem tamamlandı. Toplam süre: {t_bitis - t_baslangic:.1f}s')

    if not clean_midi:
        print('[HATA] MIDI dönüşümü başarısız oldu, işlem iptal.')
        return {"error": "MIDI dönüşümü başarısız oldu (Basic Pitch). Terminal loglarına bak."}

    # ADIM 4: Matematiksel Analiz 
    # clean_midi (Thread 2'den) ve web_chords (Thread 1'den) hazır hale geldi. Artık ton, tempo ve akor analizi yapılır.

    print('\n Matematiksel Analiz Başlıyor.')
    pm = pretty_midi.PrettyMIDI(clean_midi)

    # Ortalama chroma vektorunden ton ve mod tespiti (Pearson korelasyonu).
    # Ilk iki aday cok yakinsa NOTR akor dizisiyle tie-break yapilir.
    # Son %15'e 2x agirlik: sarki bitisleri tonik kaniti tasir (kadans onyargisi)
    chroma_avg = math_theory.weighted_chroma_average(pm.get_chroma())
    chroma_full = pm.get_chroma(fs=2)
    adaylar = math_theory.estimate_mode_v3_adaylar(chroma_avg, top_n=2)
    if len(adaylar) == 2 and (adaylar[0][2] - adaylar[1][2]) < math_theory.TIE_BREAK_MARGIN:
        notr_seq = [
            c for c in (math_theory.identify_complex_chord(chroma_full[:, i]) for i in range(chroma_full.shape[1]))
            if c
        ]
        detected_key, detected_mode = math_theory.tie_break_key(adaylar, notr_seq)
    else:
        detected_key, detected_mode = (adaylar[0][0], adaylar[0][1]) if adaylar else ("Bilinmiyor", "Bilinmiyor")

    # WAV dosyasindan hassas tempo tespiti (librosa beat tracking, ilk 60sn)
    tempo = get_accurate_tempo(wav_path)

    # Saniyede 2 örnekle chroma zaman serisi -> akor dizisi (yukarida hesaplandi)
    chord_seq = []
    for i in range(chroma_full.shape[1]):
        c = math_theory.identify_complex_chord(
            chroma_full[:, i],
            detected_key=detected_key,
            detected_mode=detected_mode
        )
        if c:
            chord_seq.append(c)

    # Gürültü filtresi: toplam sürenin %5'inden az görünen akorları gözardı et
    chord_counts = collections.Counter(chord_seq)
    threshold = len(chord_seq) * 0.05
    final_chords = [c for c, count in chord_counts.most_common(12) if count > threshold]

    # Filtre çok katıysa ve hiç akor kalmadiysa en az 4 akor garanti et
    if not final_chords:
        final_chords = [c[0] for c in chord_counts.most_common(4)]

    print(f'   => Bulunan Ton    : {detected_key} {detected_mode}')
    print(f'   => Tempo          : {int(tempo)} BPM')
    print(f'   => Audio Akorlar  : {final_chords}')

    # Web sonuçlarını da raporla (Thread 1 tarafindan paralelde hazirlanmıştı)
    if web_chords.get('success'):
        print(f"   => Web Akorları   : {web_chords['unique_chords']}")
        print(f"   => Web Kaynak     : {web_chords.get('source_url', '?')}")
    else:
        print(f"   => Web Sonucu     : Bulunamadı ({web_chords.get('error', 'bilinmeyen hata')})")

    # ADIM 5: LLM RAPORU
    # Hem web_chords (Thread 1) hem audio_data_packet (ADIM 4) hazır hale geldi. Artık generate_music_report() her iki kaynağı birleştirerek rapor uretir.

    audio_data_packet = {
        'name':   f'{artist_name} - {song_title}',
        'key':    detected_key,
        'mode':   detected_mode,
        'tempo':  tempo,
        'chords': final_chords
    }

    final_report = llm_agent.generate_music_report(audio_data_packet, web_chords)

    # Analiz sonucunu DB'ye kaydet
    try:
        db_init()
        song_id = db_get_or_create_song(
            filename=f"{artist_name} - {song_title}",
            artist=artist_name,
            title=song_title,
        )
        db_save_analysis(
            song_id=song_id,
            analyzer="full",
            detected_key=detected_key,
            detected_mode=detected_mode,
            tempo=tempo,
            chords=final_chords,
            chord_sequence=chord_seq,
            web_chords=web_chords,
        )
        print("[DB] Analiz kaydedildi.")
    except Exception as e:
        print(f"[DB] Kayıt hatası (analiz etkilenmedi): {e}")

    print('\n' + '=' * 70)
    print('HARMONAI FINAL RAPORU [ASYNC]')
    print('=' * 70)
    print(final_report.encode('utf-8', errors='replace').decode('utf-8'))

    return {
        "final_report": final_report,
        "detected_key": detected_key,
        "detected_mode": detected_mode,
        "tempo": tempo,
        "final_chords": final_chords,
        "chord_sequence": chord_seq,
        "web_chords": web_chords
    }


async def run_harmonai_pipeline_fast(url_or_path: str, artist_name: str, song_title: str, language: str = "tr"):
    """
    Basic Pitch olmadan, librosa tabanlı hızlı analiz pipeline'ı.
    Web scraping ile paralel çalışır; MIDI dönüşümü yapılmaz.

    Parametreler:
        url_or_path  : YouTube linki veya lokal WAV yolu
        artist_name  : Sanatçı adı (web scraping ve rapor için)
        song_title   : Şarkı adı
        language     : "tr" Türkçe akor siteleri | "en" Batı siteleri
    """
    print('=' * 70)
    print(f'HarmonAI (FAST) Başlatılıyor: {artist_name} - {song_title}')
    print('=' * 70)

    output_folder = 'analyzed_songs'
    os.makedirs(output_folder, exist_ok=True)

    # ADIM 1: Ses dosyasını hazırla
    wav_path = None
    if url_or_path.startswith(('http://', 'https://')):
        wav_path, _ = audio_core.process_youtube_link(url_or_path, output_folder)
    else:
        if os.path.exists(url_or_path):
            wav_path = url_or_path
        else:
            print('[HATA] Dosya bulunamadı.')
            return {"error": f"Dosya bulunamadı: {url_or_path}"}

    if not wav_path:
        print('[HATA] YouTube indirme başarısız.')
        return {
            "error": (
                "YouTube'dan ses indirilemedi.\n\n"
                "Olası sebepler:\n"
                "• Arka planda auto_builder çalışıyorsa YouTube rate-limit uygular — durdurup tekrar dene\n"
                "• Video bölge kısıtlamalı veya kaldırılmış\n"
                "• YouTube bot koruması tetiklendi — birkaç dakika bekle veya VPN aç"
            )
        }

    # ADIM 2: Paralel — web scraping + librosa analizi
    print('\n Paralel işlemler başlatılıyor:')
    print('   -> [Thread 1] Web İstihbaratı : scrape_chords_from_web()')
    print('   -> [Thread 2] Hızlı Analiz    : fast_analyzer.analyze_wav_fast()')
    print('-' * 70)

    t_baslangic = time.perf_counter()

    # Web scraping ve librosa analizi senkron oldugundan ikisi de
    # asyncio.to_thread ile devredilir; asyncio.gather paralel calistirir.
    web_chords, analiz = await asyncio.gather(
        asyncio.to_thread(web_scraper.scrape_chords_from_web, artist_name, song_title, language),
        asyncio.to_thread(fast_analyzer.analyze_wav_fast, wav_path),
    )

    t_bitis = time.perf_counter()
    print(f'\n Paralel işlem tamamlandı. Toplam süre: {t_bitis - t_baslangic:.1f}s')

    if analiz.get("error"):
        print(f'[HATA] fast_analyzer: {analiz["error"]}')
        return {"error": f"Ses analizi başarısız: {analiz['error']}"}

    detected_key   = analiz["key"]
    detected_mode  = analiz["mode"]
    tempo          = analiz["tempo"]
    final_chords   = analiz["final_chords"]
    chord_seq      = analiz["chord_sequence"]

    print(f'   => Ton      : {detected_key} {detected_mode}')
    print(f'   => Tempo    : {int(tempo)} BPM')
    print(f'   => Akorlar  : {final_chords}')

    if web_chords.get('success'):
        print(f"   => Web Akorları : {web_chords['unique_chords']}")
    else:
        print(f"   => Web Sonucu   : Bulunamadı ({web_chords.get('error', '?')})")

    # ADIM 3: LLM raporu
    audio_data_packet = {
        'name':   f'{artist_name} - {song_title}',
        'key':    detected_key,
        'mode':   detected_mode,
        'tempo':  tempo,
        'chords': final_chords,
    }

    final_report = llm_agent.generate_music_report(audio_data_packet, web_chords)

    # Analiz sonucunu DB'ye kaydet
    try:
        db_init()
        song_id = db_get_or_create_song(
            filename=f"{artist_name} - {song_title}",
            artist=artist_name,
            title=song_title,
        )
        db_save_analysis(
            song_id=song_id,
            analyzer="fast",
            detected_key=detected_key,
            detected_mode=detected_mode,
            tempo=tempo,
            chords=final_chords,
            chord_sequence=chord_seq,
            web_chords=web_chords,
        )
        print("[DB] Analiz kaydedildi.")
    except Exception as e:
        print(f"[DB] Kayıt hatası (analiz etkilenmedi): {e}")

    print('\n' + '=' * 70)
    print('HARMONAI FINAL RAPORU [FAST]')
    print('=' * 70)
    print(final_report.encode('utf-8', errors='replace').decode('utf-8'))

    return {
        "final_report":   final_report,
        "detected_key":   detected_key,
        "detected_mode":  detected_mode,
        "tempo":          tempo,
        "final_chords":   final_chords,
        "chord_sequence": chord_seq,
        "web_chords":     web_chords,
    }
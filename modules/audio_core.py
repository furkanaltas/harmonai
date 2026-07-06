import os
import sys
import glob
import contextlib
import io
import pretty_midi
import numpy as np
import librosa
from yt_dlp import YoutubeDL

os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
os.environ.setdefault('TF_ENABLE_ONEDNN_OPTS', '0')

import logging
logging.getLogger('tensorflow').setLevel(logging.ERROR)
logging.getLogger('root').setLevel(logging.ERROR)

import warnings
warnings.filterwarnings('ignore')

with contextlib.redirect_stderr(io.StringIO()):
    from basic_pitch.inference import predict_and_save
    from basic_pitch import ICASSP_2022_MODEL_PATH

# ONNX backend CPU'da TF'den belirgin hızlıdır; model dosyası mevcutsa tercih et.
try:
    from basic_pitch import build_icassp_2022_model_path, FilenameSuffix
    _onnx_yolu = build_icassp_2022_model_path(FilenameSuffix.onnx)
    BP_MODEL_PATH = _onnx_yolu if os.path.exists(str(_onnx_yolu)) else ICASSP_2022_MODEL_PATH
except Exception:
    BP_MODEL_PATH = ICASSP_2022_MODEL_PATH

# SES VE MIDI İŞLEME

def process_youtube_link(url, output_folder="youtube_downloads"):

    #YouTube linkini alır, şarkıyı WAV formatında indirir.
  
    if not os.path.exists(output_folder): 
        os.makedirs(output_folder)
        
    print(f" YouTube'dan indiriliyor: {url}")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'wav',
            'preferredquality': '192'
        }],
        'outtmpl': os.path.join(output_folder, '%(title)s.%(ext)s'),
        'quiet': False,
        'no_warnings': False,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base = ydl.prepare_filename(info).rsplit('.', 1)[0]
            wav_path = f"{base}.wav"
            sarki_adi = info.get('title', 'Bilinmeyen_Sarki')
            return wav_path, sarki_adi

    except Exception as e:
        hata = str(e)
        if 'HTTP Error 429' in hata or 'Too Many Requests' in hata:
            print(f"[HATA] YouTube rate limit (429) — çok fazla istek yapıldı. Birkaç dakika bekle.")
        elif 'Sign in' in hata or 'bot' in hata.lower():
            print(f"[HATA] YouTube bot koruması tetiklendi. VPN dene veya bekle.")
        elif 'available' in hata.lower() or 'blocked' in hata.lower():
            print(f"[HATA] Video bölge kısıtlamalı veya kaldırılmış.")
        else:
            print(f"[HATA] YouTube indirme: {hata}")
        return None, None

def _trim_wav(wav_path, output_folder, max_sure_sn):
    """Sesin ilk max_sure_sn saniyesini ayrı bir WAV olarak yazar (cache'li).
    Başarısız olursa None döner ve çağıran tam sesi kullanır."""
    import soundfile as sf
    base = os.path.splitext(os.path.basename(wav_path))[0]
    hedef = os.path.join(output_folder, f"{base}_trim{max_sure_sn}.wav")
    if os.path.exists(hedef):
        return hedef
    try:
        y, sr = librosa.load(wav_path, sr=None, mono=True, duration=max_sure_sn)
        sf.write(hedef, y, sr)
        return hedef
    except Exception as e:
        print(f"   [trim] Kırpma başarısız, tam ses kullanılacak: {e}")
        return None


def audio_to_midi(wav_path, output_folder, max_sure_sn=None):

    # WAV dosyasını Basic Pitch ile MIDI notalarına çevirir.
    # max_sure_sn verilirse ses önce o süreye kırpılır (interaktif analizde hız
    # için; dataset_builder tam şarkıyı kullanır).

    print(" Ses MIDI'ye Çevriliyor (Basic Pitch)...")
    if max_sure_sn:
        kirpilmis = _trim_wav(wav_path, output_folder, max_sure_sn)
        if kirpilmis:
            wav_path = kirpilmis
    base_name = os.path.splitext(os.path.basename(wav_path))[0]

    # Basic Pitch çıktı adı deterministiktir: <girdi_adı>_basic_pitch.mid
    # Eşzamanlı çalışmada (auto_builder + app) getctime'a göre "en yeni .mid"
    # seçmek yanlış dosyayı yakalayabilir; önce beklenen adı doğrudan kontrol et.
    beklenen = os.path.join(output_folder, f"{base_name}_basic_pitch.mid")
    if os.path.exists(beklenen):
        print(f"     Önceden analiz edilmiş MIDI bulundu. Tekrar çevrilmiyor.")
        return beklenen

    try:
        predict_and_save(
            [wav_path], 
            output_directory=output_folder, 
            save_midi=True, 
            sonify_midi=False, 
            save_model_outputs=False, 
            save_notes=False, 
            model_or_model_path=BP_MODEL_PATH
        )
    except Exception as e:
        hata_mesaji = str(e)
        if "already exists" in hata_mesaji:
            print("   Dosya zaten varmış (Hata yakalandı ve atlatıldı).")
            if os.path.exists(beklenen):
                return beklenen
            cands = glob.glob(os.path.join(output_folder, f"*{base_name}*.mid"))
            if cands: return max(cands, key=os.path.getctime)
        else:
            print(f" Basic Pitch Dönüşüm Hatası: {e}")
            return None

    if os.path.exists(beklenen):
        return beklenen
    cands = glob.glob(os.path.join(output_folder, f"*{base_name}*.mid"))
    return max(cands, key=os.path.getctime) if cands else None

def clean_midi_drums(midi_path):

    # Oluşturulan MIDI dosyasındaki davul/perküsyon kanallarını siler.
    # Tüm melodik notaları tek bir piyano kanalında birleştirerek temizler.

    print(" Ritmik gürültüler (Davullar) temizleniyor...")
    try:
        pm = pretty_midi.PrettyMIDI(midi_path)
        yeni_pm = pretty_midi.PrettyMIDI()

        melodik_enst = [i for i in pm.instruments if not i.is_drum]

        if not melodik_enst: 
            return midi_path
            
        # Notaları tek kanalda birleştirir.
        yeni_inst = pretty_midi.Instrument(program=0, is_drum=False, name="Cleaned_Track")
        for i in melodik_enst: 
            yeni_inst.notes.extend(i.notes)
            
        yeni_inst.notes.sort(key=lambda x: x.start)
        yeni_pm.instruments.append(yeni_inst)
            
        cikis_yolu = midi_path.replace(".mid", "_davulsuz.mid").replace("_basic_pitch", "")
        yeni_pm.write(cikis_yolu)
        
        return cikis_yolu
        
    except Exception as e:
        print(f"❌ MIDI Temizleme Hatası: {e}")
        return midi_path


def get_accurate_tempo(wav_path: str) -> float:
    """WAV dosyasından (ilk 60 saniye) beat tracking ile tempo ölçer."""
    try:
        y, sr = librosa.load(wav_path, sr=None, duration=60)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        return float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
    except Exception as e:
        print(f"Tempo hesaplama hatası: {e}")
        return 120.0
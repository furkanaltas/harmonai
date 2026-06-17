import os
import sys
import glob
import contextlib
import io
import pretty_midi
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
        'quiet': True, 
        'no_warnings': True
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            base = ydl.prepare_filename(info).rsplit('.', 1)[0]
            wav_path = f"{base}.wav"
            sarki_adi = info.get('title', 'Bilinmeyen_Sarki')
            return wav_path, sarki_adi
            
    except Exception as e: 
        print(f" YouTube İndirme Hatası: {e}")
        return None, None

def audio_to_midi(wav_path, output_folder):

    # WAV dosyasını Basic Pitch ile MIDI notalarına çevirir.

    print(" Ses MIDI'ye Çevriliyor (Basic Pitch)...")
    base_name = os.path.splitext(os.path.basename(wav_path))[0]

    mevcut_midiler = glob.glob(os.path.join(output_folder, f"*{base_name}*basic_pitch.mid"))
    if mevcut_midiler:
        print(f"     Önceden analiz edilmiş MIDI bulundu. Tekrar çevrilmiyor.")
        return mevcut_midiler[0]

    try:
        predict_and_save(
            [wav_path], 
            output_directory=output_folder, 
            save_midi=True, 
            sonify_midi=False, 
            save_model_outputs=False, 
            save_notes=False, 
            model_or_model_path=ICASSP_2022_MODEL_PATH
        )
    except Exception as e:
        hata_mesaji = str(e)
        if "already exists" in hata_mesaji:
            print("   Dosya zaten varmış (Hata yakalandı ve atlatıldı).")
            cands = glob.glob(os.path.join(output_folder, "*.mid"))
            if cands: return max(cands, key=os.path.getctime)
        else:
            print(f" Basic Pitch Dönüşüm Hatası: {e}")
            return None

    cands = glob.glob(os.path.join(output_folder, f"*{base_name}*basic_pitch.mid"))
    if not cands:
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
import numpy as np
import librosa
from scipy.stats import pearsonr
import re

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# Tonal hierarchy weights — Tez 3.6, Symbols table
# α: strong/tonic note (karar/güçlü perde)
# β: characteristic note (karakteristik perde)
# γ: diatonic passing note (diyatonik perde)
# ε: chromatic background note (kromatik nota)
ALPHA: float = 1.0
BETA: float = 0.8
GAMMA: float = 0.5
EPSILON: float = 0.1

# Bayesian context bonus applied to cosine similarity scoring — thesis §3.2
CB: float = 0.15

CHORD_DEFINITIONS = {}
for i, root in enumerate(NOTE_NAMES):
    # Major ve Minor Akorlar
    vec = np.zeros(12); vec[[i, (i+4)%12, (i+7)%12]] = 1; CHORD_DEFINITIONS[f"{root}"] = vec       # Major
    vec = np.zeros(12); vec[[i, (i+3)%12, (i+7)%12]] = 1; CHORD_DEFINITIONS[f"{root}m"] = vec      # Minor
    
    # Diminished ve Augmented Akorlar
    vec = np.zeros(12); vec[[i, (i+3)%12, (i+6)%12]] = 1; CHORD_DEFINITIONS[f"{root}dim"] = vec    # Diminished
    vec = np.zeros(12); vec[[i, (i+4)%12, (i+8)%12]] = 1; CHORD_DEFINITIONS[f"{root}aug"] = vec    # Augmented
    
    # Suspended (Askıda Kalan) Akorlar
    vec = np.zeros(12); vec[[i, (i+2)%12, (i+7)%12]] = 1; CHORD_DEFINITIONS[f"{root}sus2"] = vec   # Sus2
    vec = np.zeros(12); vec[[i, (i+5)%12, (i+7)%12]] = 1; CHORD_DEFINITIONS[f"{root}sus4"] = vec   # Sus4

    # Yedililer
    vec = np.zeros(12); vec[[i, (i+4)%12, (i+7)%12, (i+10)%12]] = 1; CHORD_DEFINITIONS[f"{root}7"] = vec # Dominant7
    vec = np.zeros(12); vec[[i, (i+4)%12, (i+7)%12, (i+11)%12]] = 1; CHORD_DEFINITIONS[f"{root}maj7"] = vec # Maj7
    vec = np.zeros(12); vec[[i, (i+3)%12, (i+7)%12, (i+10)%12]] = 1; CHORD_DEFINITIONS[f"{root}m7"] = vec   # Min7

# Ton ve Mod Profilleri 
PROFILES_V3 = {
    'Major': [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    'Minor': [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    'Harmonic Minor': [6.0, 2.0, 3.5, 5.0, 2.5, 4.0, 2.0, 5.0, 4.5, 2.0, 5.5, 2.0], 
    'Melodic Minor':  [6.0, 2.0, 3.5, 4.5, 2.5, 4.0, 2.0, 5.0, 3.5, 4.5, 5.0, 2.0],
    'Hicaz': [6.0, 5.5, 1.5, 4.0, 5.0, 4.5, 2.0, 5.0, 3.0, 2.5, 5.0, 2.0],
    'Dorian': [6.0, 2.5, 3.5, 5.0, 3.0, 4.0, 3.5, 5.0, 3.0, 4.5, 3.5, 2.5],
    'Phrygian (Kürdi)': [6.0, 5.0, 3.5, 4.5, 3.0, 3.5, 2.5, 5.0, 4.0, 2.5, 3.5, 2.5],
    'Mixolydian': [6.0, 2.0, 3.5, 2.5, 4.5, 4.0, 2.5, 5.0, 2.5, 3.5, 5.0, 2.5],
    'Locrian': [5.0, 5.0, 3.0, 4.0, 2.0, 5.0, 4.5, 2.0, 4.0, 2.5, 4.0, 3.0],
    'Lydian': [5.5, 2.5, 4.0, 3.0, 5.0, 3.5, 5.5, 5.0, 2.5, 4.0, 2.5, 3.0]
}

# Analiz ve tanımlama fonksiyonları

def identify_complex_chord(chroma_vector, threshold=0.60, detected_key=None, detected_mode=None):
    """
    Verilen kroma vektörüne en yakın akoru bulur.
    Eğer detected_key ve detected_mode verilirse, şarkının tonuna uygun (diatonik) akorlara bonus puan vererek müzikal bir seçim yapar.
    """
    if np.sum(chroma_vector) == 0: 
        return None
        
    # Aşağıda yaptığımız işlemle şarkının tonuna/moduna uygun notalara öncelik veriyoruz.
    tonality_weights = np.ones(12) # Varsayılan olarak tüm notaların çarpanı 1.0
    
    if detected_key and detected_mode and detected_mode in PROFILES_V3:
        try:
            key_idx = NOTE_NAMES.index(detected_key)
            mode_profile = PROFILES_V3[detected_mode]
            
            # Seçilen modun (örn: Minör) profilini, şarkının tonuna (örn: B) doğru kaydırır.
            shifted_profile = np.roll(mode_profile, key_idx)
            tonality_weights = 1.0 + (shifted_profile / np.max(shifted_profile)) * CB
        except:
            pass 

    best_c, max_sim = None, -1
    norm_vec = chroma_vector / (np.linalg.norm(chroma_vector) + 1e-10) 
    
    for name, template in CHORD_DEFINITIONS.items():
        norm_temp = template / (np.linalg.norm(template) + 1e-10)
        base_sim = np.dot(norm_vec, norm_temp)
        
        # Akorun kök sesini bul (Örn: "C#sus4" ise "C#", "Am7" ise "A")
        root_match = re.match(r"^([A-G][#]?)", name)
        bonus = 1.0
        if root_match:
            root_note = root_match.group(1)
            if root_note in NOTE_NAMES:
                root_idx = NOTE_NAMES.index(root_note)
                bonus = tonality_weights[root_idx] # Akorun kök sesi tonun içindeyse akor bonusu puanı elde eder.
                
        # Nihai benzerlik skoru = Matematiksel Benzerlik * Müzikal Mantık Bonusu
        final_sim = base_sim * bonus
        
        if final_sim > max_sim: 
            max_sim = final_sim
            best_c = name
    
    return best_c if max_sim > threshold else None

def estimate_mode_v3(chroma_vector):

    #Şarkının genel kroma ortalamasını alıp Pearson Korelasyonu ile Ton ve Mod tahmini yapar.

    if np.sum(chroma_vector) == 0: 
        return "Bilinmiyor", "Bilinmiyor"
        
    norm = chroma_vector / (np.max(chroma_vector) + 1e-10)
    best_r, best_k, best_m = -1, "C", "Bilinmiyor"
    
    for i in range(12):
        shifted = np.roll(norm, -i)
        for m_name, m_prof in PROFILES_V3.items():
            r, _ = pearsonr(shifted, m_prof)
            if r > best_r: 
                best_r = r
                best_k = NOTE_NAMES[i]
                best_m = m_name
                
    return best_k, best_m

def get_accurate_tempo(wav_path):

    # Librosa kullanarak ses dosyasından (ilk 60 saniye) hassas tempo ölçümü yapar.
    
    try:
        y, sr = librosa.load(wav_path, sr=None, duration=60)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        
        if isinstance(tempo, np.ndarray):
            return float(tempo[0])
        return float(tempo)
    except Exception as e: 
        print(f"Tempo hesaplama hatası: {e}")
        return 120.0
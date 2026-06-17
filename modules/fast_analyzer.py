"""
fast_analyzer.py — Basic Pitch gerektirmeyen, librosa tabanlı hızlı armoni analizi.

Ana pipeline (harmonai_pipeline.py) Basic Pitch ile WAV→MIDI dönüşümü yapıp
~60-90 saniye harcıyor. Bu modül aynı matematiksel analizi (ton, tempo, akor dizisi)
doğrudan WAV üzerinden librosa ile ~5-10 saniyede gerçekleştirir.

Fark:
  - Basic Pitch  : nota bazlı (hangi tuşa basıldı → MIDI)
  - Bu modül     : spektral (frekans enerjisi → kroma vektörü)
  Chord detection için ikisi de 12-dim kroma vektörü üretir; sonuç kalitesi benzerdir.

Kullanım:
  from modules.fast_analyzer import analyze_wav_fast
  result = analyze_wav_fast("sarkı.wav")
"""

import numpy as np
import librosa
from modules.math_theory import (
    identify_complex_chord,
    estimate_mode_v3,
    get_accurate_tempo,
    NOTE_NAMES,
)
import collections


# Saniyede kaç kroma çerçevesi analiz edilecek (4 = 0.25sn'de bir kare)
# Daha yüksek → daha ince zaman çözünürlüğü, temporal smoothing'den önce daha fazla ham veri
_FS: int = 4

# Temporal smoothing pencere boyutu (kare sayısı)
# 4 kare × 0.25sn = 1 saniyelik pencere → her karar 1sn'lik kroma ortalamasına dayanır
_SMOOTH_WINDOW: int = 4

# Toplam akor havuzunun en az bu oranında görünmeyen akorlar gürültü sayılır
_FREQ_THRESHOLD: float = 0.05

# En fazla kaç farklı akor raporlanır
_MAX_CHORDS: int = 12

# Minimum garanti akor sayısı (filtre çok katı olursa devreye girer)
_MIN_CHORDS: int = 4


def _extract_chroma(wav_path: str, fs: int = _FS) -> np.ndarray:
    """
    WAV dosyasından 12 x T boyutlu kroma matrisi çıkarır.
    hop_length, fs parametresinden hesaplanır (sr / fs).
    """
    y, sr = librosa.load(wav_path, sr=None, mono=True)
    hop_length = max(1, int(sr / fs))
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, hop_length=hop_length, norm=2)
    return chroma


def _smooth_chroma(chroma: np.ndarray, window: int = _SMOOTH_WINDOW) -> np.ndarray:
    """
    Temporal smoothing: her zaman adımı için [t-window//2 : t+window//2] aralığındaki
    karelerin ortalamasını alır. Bu sayede anlık gürültü (tek karede beliren yanlış nota)
    komşu kareler tarafından bastırılır ve akor kararları daha tutarlı hale gelir.

    Örnek (window=4, fs=4):
        Ham: [Am, C, Am, Am, G, Am, G, G]  ← tek C ve tek G gürültü olabilir
        Smooth: [Am, Am, Am, Am, G, G, G, G]  ← geçişler netleşir
    """
    T = chroma.shape[1]
    smoothed = np.zeros_like(chroma)
    half = window // 2
    for t in range(T):
        baslangic = max(0, t - half)
        bitis = min(T, t + half + 1)
        smoothed[:, t] = chroma[:, baslangic:bitis].mean(axis=1)
    return smoothed


def _build_chord_sequence(chroma: np.ndarray, key: str, mode: str) -> list[str]:
    """
    Smoothed kroma üzerinden akor dizisi oluşturur.
    Önce temporal smoothing uygulanır, ardından her kareye akor tespiti yapılır.
    """
    smoothed = _smooth_chroma(chroma)
    seq = []
    for t in range(smoothed.shape[1]):
        chord = identify_complex_chord(smoothed[:, t], detected_key=key, detected_mode=mode)
        if chord:
            seq.append(chord)
    return seq


def _filter_chords(chord_seq: list[str]) -> list[str]:
    """
    Nadir akorları (%5 altı) temizler, en sık görülen MAX_CHORDS adeti döndürür.
    Tamamı filtrelenirse en az MIN_CHORDS akor garanti edilir.
    """
    if not chord_seq:
        return []

    counts = collections.Counter(chord_seq)
    threshold = len(chord_seq) * _FREQ_THRESHOLD
    filtered = [c for c, n in counts.most_common(_MAX_CHORDS) if n > threshold]

    if not filtered:
        filtered = [c for c, _ in counts.most_common(_MIN_CHORDS)]

    return filtered


def analyze_wav_fast(wav_path: str) -> dict:
    """
    WAV dosyasını MIDI dönüşümü olmadan doğrudan analiz eder.

    Parametreler:
        wav_path : Analiz edilecek WAV dosyasının yolu

    Döndürür:
        {
            "key"           : str   (örn. "A")
            "mode"          : str   (örn. "Hicaz")
            "tempo"         : float (BPM)
            "final_chords"  : list[str]   (filtrelenmiş benzersiz akorlar)
            "chord_sequence": list[str]   (ham zaman-sıralı akor dizisi)
            "error"         : str | None  (hata varsa mesaj, yoksa None)
        }
    """
    try:
        print(f"[fast_analyzer] Kroma çıkarılıyor: {wav_path}")
        chroma = _extract_chroma(wav_path)

        # Ton ve mod tespiti (ortalama kroma → Pearson korelasyonu)
        chroma_avg = chroma.mean(axis=1)
        key, mode = estimate_mode_v3(chroma_avg)
        print(f"[fast_analyzer] Ton: {key} {mode}")

        # Tempo tespiti (beat tracking, ilk 60sn)
        tempo = get_accurate_tempo(wav_path)
        print(f"[fast_analyzer] Tempo: {int(tempo)} BPM")

        # Akor dizisi
        chord_seq = _build_chord_sequence(chroma, key, mode)
        final_chords = _filter_chords(chord_seq)
        print(f"[fast_analyzer] Akorlar: {final_chords}")

        return {
            "key": key,
            "mode": mode,
            "tempo": tempo,
            "final_chords": final_chords,
            "chord_sequence": chord_seq,
            "error": None,
        }

    except Exception as exc:
        print(f"[fast_analyzer] Hata: {exc}")
        return {
            "key": "Bilinmiyor",
            "mode": "Bilinmiyor",
            "tempo": 0.0,
            "final_chords": [],
            "chord_sequence": [],
            "error": str(exc),
        }

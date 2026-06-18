import glob
import os
import numpy as np
import pandas as pd
import pretty_midi
import matplotlib.pyplot as plt
import seaborn as sns
from modules import math_theory


AKOR_ETIKETLERI: list[str] = list(math_theory.CHORD_DEFINITIONS.keys())

# Thesis §3.3: dynamic thresholding — chords with p(a) = f(a)/N < ALPHA_THRESHOLD
# are excluded from a song's chord sequence before transition counting.
ALPHA_THRESHOLD: float = 0.05


def _toDataFrame(matrix, labels=None):
    if isinstance(matrix, pd.DataFrame):
        return matrix.copy()
    if labels is None:
        raise ValueError("labels=None iken NumPy matris verildi. Etiket listesi (akor isimleri) zorunlu.")
    return pd.DataFrame(matrix, index=labels, columns=labels)


def getMidiListFromFolder(folder_path: str) -> list[str]:
    # Tüm MIDI dosyalarını bulmak için glob kullanarak klasör içinde ve alt klasörlerde arama yapar.
    pattern = os.path.join(folder_path, "**", "*.mid*")
    return glob.glob(pattern, recursive=True)


def getChordSequenceFromMidi(midi_path: str, fs: int = 2) -> list[str]:
    # MIDI dosyasını yükle ve zaman tabanlı kromatik özellikleri çıkar.
    try:
        pm = pretty_midi.PrettyMIDI(midi_path)
    except Exception:
        return []

    chroma = pm.get_chroma(fs=fs)
    chords: list[str] = []

    for t in range(chroma.shape[1]):
        v = chroma[:, t]
        c = math_theory.identify_complex_chord(v)
        if c:
            chords.append(c)

    return chords


def compressChordSequence(chords: list[str]) -> list[str]:
    # Eğer akor dizisinde tekrarlayan akorlar varsa, bunları tek bir örnekle sıkıştırır. Örneğin, ['Am', 'Am', 'G', 'G'] → ['Am', 'G'].
    if not chords:
        return []
    result = [chords[0]]
    for c in chords[1:]:
        if c != result[-1]:
            result.append(c)
    return result


def generateTransitionMatrix(folder_path: str, dataset_name: str = "Dataset") -> pd.DataFrame:

    """
    108x108'lik bir Markov geçiş matrisi oluşturmak için folder_path içindeki tüm MIDI dosyalarını tarar.
    Dinamik eşikleme uygular (ALPHA_THRESHOLD = 0.05) tez 3.8'e göre:
    Bir şarkı içindeki göreli frekansı p(a) = f(a)/N < 0.05 olan akorlar, geçiş sayımından önce elenir.
    """
    midi_list = getMidiListFromFolder(folder_path)
    n_songs = len(midi_list)

    transition_counter = pd.DataFrame(
        0, index=AKOR_ETIKETLERI, columns=AKOR_ETIKETLERI, dtype=np.int64
    )

    print(f"🔄 {dataset_name} için Markov geçiş analizi başlıyor... ({n_songs} dosya)")

    for idx, midi_path in enumerate(midi_list, start=1):
        chord_seq = getChordSequenceFromMidi(midi_path)
        chord_seq = compressChordSequence(chord_seq)

        if len(chord_seq) < 2:
            continue

        # Dinamik eşikleme: nadir akorları filtrele (tez 3.5, α ≈ 0.05)
        n = len(chord_seq)
        freq_dist: dict[str, int] = {}
        for c in chord_seq:
            freq_dist[c] = freq_dist.get(c, 0) + 1
        chord_seq = [c for c in chord_seq if freq_dist[c] / n >= ALPHA_THRESHOLD]

        if len(chord_seq) < 2:
            continue

        for a, b in zip(chord_seq[:-1], chord_seq[1:]):
            if a in transition_counter.index and b in transition_counter.columns:
                transition_counter.loc[a, b] += 1

        if idx % 50 == 0 or idx == n_songs:
            print(f"   [{dataset_name}] İşlenen: {idx}/{n_songs}")

    print(f"✅ {dataset_name} geçiş matrisi üretildi.")
    return transition_counter


def getTopTransitions(matrix, top_n: int = 20) -> pd.DataFrame:
    """Ham geçiş sayım matrisindeki en sık geçişleri döndürür."""
    df = _toDataFrame(matrix)
    stacked = df.stack().reset_index()
    stacked.columns = ["from_chord", "to_chord", "value"]
    stacked = stacked[stacked["value"] > 0]
    return stacked.sort_values("value", ascending=False).head(top_n).reset_index(drop=True)


def computeDiffMatrix(turk_matrix, bati_matrix) -> pd.DataFrame:
    """
    Her iki matrisi de satır-normalize edip ve fark matrisini Δ = P_TR - P_BATI olarak döndürür. 
    Bu, tez 3.8'teki kültürlerarası delta matrisine karşılık gelir.
    """
    turk_df = _toDataFrame(turk_matrix)
    bati_df = _toDataFrame(bati_matrix, labels=turk_df.index.tolist())

    turk_norm = turk_df.div(turk_df.sum(axis=1).replace(0, np.nan), axis=0)
    bati_norm = bati_df.div(bati_df.sum(axis=1).replace(0, np.nan), axis=0)

    return (turk_norm - bati_norm).fillna(0.0)


def getMostDistinctiveTransitions(turk_matrix, bati_matrix, top_n: int = 30) -> pd.DataFrame:
    """
    Kültürel olarak en ayırt edici geçişleri delta matrisini kullanarak döndürür.
    Pozitif fark → Türkçe baskın; negatif fark → Batı baskın.
    """
    diff = computeDiffMatrix(turk_matrix, bati_matrix)

    stacked = diff.stack().reset_index()
    stacked.columns = ["from_chord", "to_chord", "diff"]
    stacked = stacked[stacked["diff"] != 0]

    top_pos = stacked.sort_values("diff", ascending=False).head(top_n // 2)
    top_neg = stacked.sort_values("diff", ascending=True).head(top_n // 2)

    return pd.concat([top_pos, top_neg], ignore_index=True)


def plotTransitionHeatmap(matrix, title: str = "", vmax: float | None = None, figsize=(10, 8)):
    # Geçiş matrisini DataFrame'e çevir, ardından seaborn ile ısı haritası olarak görselleştir. 
    # Fark matrisi için özel renk haritası ve merkezleme uygula.
    df = _toDataFrame(matrix)

    plt.figure(figsize=figsize)
    sns.heatmap(
        df,
        cmap="magma" if "fark" not in title.lower() else "coolwarm",
        vmax=vmax,
        center=0.0 if "fark" in title.lower() else None,
        cbar=True,
        square=True,
        xticklabels=False,
        yticklabels=False,
    )
    plt.title(title)
    plt.xlabel("Sonraki Akor")
    plt.ylabel("Önceki Akor")
    plt.tight_layout()
    plt.show()


def getModeTransitionProfile(matrix, mod_chords: list[str]) -> pd.DataFrame:
    """Verilen akor listesine göre geçiş alt-matrisini döndürür (hem TR hem EN için kullanılır)."""
    df = _toDataFrame(matrix)
    mevcut = [c for c in mod_chords if c in df.index]
    if not mevcut:
        raise ValueError("Verilen mod_chords listesindeki akorlar matriste bulunamadı.")
    return df.loc[mevcut, mevcut]

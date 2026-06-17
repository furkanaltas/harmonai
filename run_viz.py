import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd
from markov_models import generateTransitionMatrix, computeDiffMatrix

turk_klasor = 'veri_seti/davulsuz t\u00fcrk\u00e7e ANA dosya'
bati_klasor = 'veri_seti/davulsuz yabanc\u0131 ANA Dosya'

turk_matrix = generateTransitionMatrix(turk_klasor, 'Turkce')
bati_matrix = generateTransitionMatrix(bati_klasor, 'Bati')

turk_toplam = turk_matrix.sum(axis=0) + turk_matrix.sum(axis=1)
bati_toplam = bati_matrix.sum(axis=0) + bati_matrix.sum(axis=1)
genel_toplam = turk_toplam.add(bati_toplam, fill_value=0)
en_aktif_30_akor = genel_toplam.sort_values(ascending=False).head(30).index.tolist()

turk_alt_matris = turk_matrix.loc[en_aktif_30_akor, en_aktif_30_akor]
bati_alt_matris = bati_matrix.loc[en_aktif_30_akor, en_aktif_30_akor]

turk_norm = turk_alt_matris.div(turk_alt_matris.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
bati_norm = bati_alt_matris.div(bati_alt_matris.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)

fig, axes = plt.subplots(1, 2, figsize=(18, 8))

sns.heatmap(turk_norm, cmap='YlOrRd', ax=axes[0], cbar=True, square=True)
axes[0].set_title('Turk Muzigi - En Aktif 30 Akor Markov Gecis Matrisi', fontsize=14, fontweight='bold')
axes[0].set_xlabel('Sonraki Akor', fontsize=12)
axes[0].set_ylabel('Onceki Akor', fontsize=12)

sns.heatmap(bati_norm, cmap='YlOrRd', ax=axes[1], cbar=True, square=True)
axes[1].set_title('Bati Muzigi - En Aktif 30 Akor Markov Gecis Matrisi', fontsize=14, fontweight='bold')
axes[1].set_xlabel('Sonraki Akor', fontsize=12)
axes[1].set_ylabel('Onceki Akor', fontsize=12)

plt.suptitle('Sekil 3.4. Turk (sol) ve Bati (sag) Markov Gecis Matrislerinin Isi Haritalari', fontsize=16, fontweight='bold', y=0.01)
plt.tight_layout()
plt.savefig('sekil_3_4_markov_matrisleri.png', dpi=300, bbox_inches='tight')

fark_matrisi = computeDiffMatrix(turk_matrix, bati_matrix)
fark_alt_matris = fark_matrisi.loc[en_aktif_30_akor, en_aktif_30_akor]

plt.figure(figsize=(10, 8))
max_val = np.abs(fark_alt_matris.values).max()

sns.heatmap(
    fark_alt_matris, 
    cmap='RdBu_r', 
    center=0, 
    vmin=-max_val, 
    vmax=max_val,
    square=True, 
    cbar_kws={'label': 'Fark (Kirmizi: Turkce Baskin, Mavi: Bati Baskin)'}
)

plt.title('Sekil 3.5. Delta Fark Matrisinin Iraksan Renk Skalali Isi Haritasi', fontsize=14, fontweight='bold', y=-0.15)
plt.xlabel('Sonraki Akor', fontsize=12)
plt.ylabel('Onceki Akor', fontsize=12)
plt.tight_layout()
plt.savefig('sekil_3_5_delta_fark_matrisi.png', dpi=300, bbox_inches='tight')

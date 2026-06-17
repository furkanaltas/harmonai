import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd
from markov_models import generateTransitionMatrix, computeDiffMatrix

# 1. Klasör yolları (HarmonAI projesindeki yollara göre güncellendi)
turk_klasor = "veri_seti/davulsuz türkçe ANA dosya"
bati_klasor = "veri_seti/davulsuz yabancı ANA Dosya"

# 2. Matrislerin üretimi
turk_matrix = generateTransitionMatrix(turk_klasor, "Türkçe")
bati_matrix = generateTransitionMatrix(bati_klasor, "Batı")

# 3. Hem Türk hem Batı matrisindeki en aktif 30 akoru belirleme
turk_toplam = turk_matrix.sum(axis=0) + turk_matrix.sum(axis=1)
bati_toplam = bati_matrix.sum(axis=0) + bati_matrix.sum(axis=1)
genel_toplam = turk_toplam.add(bati_toplam, fill_value=0)
en_aktif_30_akor = genel_toplam.sort_values(ascending=False).head(30).index.tolist()

turk_alt_matris = turk_matrix.loc[en_aktif_30_akor, en_aktif_30_akor]
bati_alt_matris = bati_matrix.loc[en_aktif_30_akor, en_aktif_30_akor]

# Logaritmik ölçekleme yerine olasılıksal normalizasyon yapıyoruz (satır toplamı 1 olacak şekilde)
turk_norm = turk_alt_matris.div(turk_alt_matris.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
bati_norm = bati_alt_matris.div(bati_alt_matris.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)

fig, axes = plt.subplots(1, 2, figsize=(18, 8))

# Sol - Türk Müziği Is Haritası
sns.heatmap(turk_norm, cmap="YlOrRd", ax=axes[0], cbar=True, square=True)
axes[0].set_title("Türk Müziği - En Aktif 30 Akor Markov Geçiş Matrisi", fontsize=14, fontweight="bold")
axes[0].set_xlabel("Sonraki Akor", fontsize=12)
axes[0].set_ylabel("Önceki Akor", fontsize=12)

# Sağ - Batı Müziği Is Haritası
sns.heatmap(bati_norm, cmap="YlOrRd", ax=axes[1], cbar=True, square=True)
axes[1].set_title("Batı Müziği - En Aktif 30 Akor Markov Geçiş Matrisi", fontsize=14, fontweight="bold")
axes[1].set_xlabel("Sonraki Akor", fontsize=12)
axes[1].set_ylabel("Önceki Akor", fontsize=12)

plt.suptitle("Şekil 3.4. Türk (sol) ve Batı (sağ) Markov Geçiş Matrislerinin Isı Haritaları", fontsize=16, fontweight="bold", y=0.01)
plt.tight_layout()
plt.savefig("sekil_3_4_markov_matrisleri.png", dpi=300, bbox_inches="tight")
plt.show()
print("Şekil 3.4 sekil_3_4_markov_matrisleri.png olarak kaydedildi.")

# Delta Fark Matrisini bulalım (Türkçe - Batı) (markov_models.py icerisindeki fonksiyonu kullanyoruz)
fark_matrisi = computeDiffMatrix(turk_matrix, bati_matrix)
fark_alt_matris = fark_matrisi.loc[en_aktif_30_akor, en_aktif_30_akor]

plt.figure(figsize=(10, 8))
# Kırmızı = Türk müziğinde baskın, Mavi = Batı müziğinde baskın olması için "RdBu_r" paleti 
max_val = np.abs(fark_alt_matris.values).max()

sns.heatmap(
    fark_alt_matris, 
    cmap="RdBu_r", 
    center=0, 
    vmin=-max_val, 
    vmax=max_val,
    square=True, 
    cbar_kws={"label": "Fark (Kırmızı: Türkçe Baskın, Mavi: Batı Baskın)"}
)

plt.title("Şekil 3.5. Delta Fark Matrisinin Iraksan Renk Skalalı Isı Haritası", fontsize=14, fontweight="bold", y=-0.15)
plt.xlabel("Sonraki Akor", fontsize=12)
plt.ylabel("Önceki Akor", fontsize=12)
plt.tight_layout()
plt.savefig("sekil_3_5_delta_fark_matrisi.png", dpi=300, bbox_inches="tight")
plt.show()
print("Şekil 3.5 sekil_3_5_delta_fark_matrisi.png olarak kaydedildi!")


import json
notebook_path = 'gorsellestirme.ipynb'
with open(notebook_path, 'r', encoding='utf-8') as f:
    nb = json.load(f)

# Find the last cell and update its source
for i, line in enumerate(nb['cells'][-1]['source']):
    if 'gecis_matrisi_uret_klasorden' in line and 'turk_matrix' in line:
        nb['cells'][-1]['source'][i] = "turk_matrix = gecis_matrisi_uret_klasorden('veri_seti/davulsuz t\\u00fcrk\\u00e7e ANA dosya', 'Turkce')\\n"
    if 'gecis_matrisi_uret_klasorden' in line and 'bati_matrix' in line:
        nb['cells'][-1]['source'][i] = "bati_matrix = gecis_matrisi_uret_klasorden('veri_seti/davulsuz yabanc\\u0131 ANA Dosya', 'Bati')\\n"

with open(notebook_path, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Fixed successfully')

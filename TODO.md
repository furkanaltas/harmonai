# HarmonAI — Geliştirme Yol Haritası

Checklemek için: `- [x]` yap veya Claude'a "bunu tamamla" de.

---

## Aktif / Devam Eden

- [ ] **Dataset pipeline çalışıyor** — auto_builder.py arka planda, hedef 2000 şarkı
- [ ] **Spotify API key bekleniyor** — yeni key gelince `spotify_labeler.py` çalıştır, ground truth doldur
- [ ] **Threshold kalibrasyonu** — Spotify etiketleri dolunca ton tespit eşiğini optimize et

---

## Kısa Vadeli (Sıradaki Oturum)

- [ ] **app.py UI temizliği** — deploy öncesi minimal görsel iyileştirme (Streamlit layout)
- [ ] **Streamlit Cloud deploy** — UI temizliğinden sonra

---

## Model & Matematik Geliştirmeleri

- [ ] **Voice Leading Analysis** — akor geçişlerindeki nota hareketi yumuşaklık skoru
- [ ] **Functional Harmony** — akorları Tonik / Subdominant / Dominant olarak etiketle
- [ ] **Harmonic Rhythm** — kaç saniyede bir akor değişiyor (tempo-normalize)
- [ ] **Chord Complexity Score** — triad / 7li / extended akor oranı
- [ ] **2. derece Markov** — 3k-5k şarkı dolunca geçiş yap (şu an 1. derece)
- [ ] **Deep learning (CRNN)** — dataset 3k-5k'ya ulaşınca Random Forest yerine dene

---

## Yeni Özellikler

- [ ] **İki şarkı karşılaştırma** — "Bu iki şarkı harmonik olarak %67 benzer" çıktısı
- [ ] **Markov akor önerici** — başlangıç akoru ver, olası devamları sırala (eğitim aracı)
- [ ] **DB üzerinden arama** — "Hicaz modundaki şarkıları göster" sorgu arayüzü

---

## Tamamlanan

- [x] fast_analyzer.py — librosa tabanlı hızlı analiz (~5-10sn)
- [x] db_manager.py — SQLite iki tablolu şema (songs + analyses)
- [x] dataset_builder.py — Gemini → YouTube → MIDI otomasyonu
- [x] auto_builder.py — saatlik schedule ile arka plan dataset oluşturucu
- [x] spotify_labeler.py — Spotify API ground truth etiketleyici
- [x] Groq entegrasyonu — dataset_builder şarkı listesi için Gemini → Groq geçişi
- [x] Duplicate önleme — rastgele 80 örneklem + LIKE fuzzy DB kontrolü
- [x] Anomali düzeltmeleri — `_baglanti` private import, `get_accurate_tempo` taşıma, DB tutarlılığı

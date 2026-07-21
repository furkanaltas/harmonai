# HarmonAI — Geliştirme Yol Haritası

Checklemek için: `- [x]` yap veya Claude'a "bunu tamamla" de.

---

## Aktif / Devam Eden

- [ ] **Dataset pipeline çalışıyor** — auto_builder.py arka planda, hedef 2000 şarkı
- [x] **Spotify API key bekleniyor** — yeni key gelince `spotify_labeler.py` çalıştır, ground truth doldur
- [ ] **Threshold kalibrasyonu** — Spotify etiketleri dolunca ton tespit eşiğini optimize et

---

## Kısa Vadeli (Sıradaki Oturum)

- [x] **app.py UI temizliği** — deploy öncesi minimal görsel iyileştirme (Streamlit layout)
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

## 🤖 Makine Öğrenmesi Yol Haritası (ML)

> **Altın kural: sistemin kendi ürettiği etiketlerle (self-label) ASLA model eğitme.**
> Neden: algoritmanın hatalarını "doğru" diye ezberler (label noise / confirmation bias)
> ve tam korkulan halüsinasyon etkisini yaratır. 1930 otomatik etiket yalnızca
> keşif/istatistik içindir; eğitim ve değerlendirme SADECE bağımsız etiketlerle yapılır.

- [ ] **SymbTr korpusunu indir ve makam tarafını onunla ölç** *(en yüksek öncelik)*
  - Ne: MTG (Music Technology Group) SymbTr korpusu — ~2200 Türk makam müziği eseri,
    uzmanlarca etiketli makam + usul bilgisi. GitHub: `MTG/SymbTr` (ücretsiz, txt/MusicXML/MIDI).
  - Neden: Türk tarafı için bağımsız, uzman kaynaklı ground truth — Spotify'ın kapattığı
    boşluğu makamlar için bedavaya kapatır.
  - Nasıl: (1) repo klonla, (2) SymbTr makam adlarını bizim profillere eşleyen tablo yaz
    (örn. Hicaz/Hicazkar/Uzzal → Hicaz; Kürdi/Kürdilihicazkar → Phrygian (Kürdi);
    eşleşmeyenleri "kapsam dışı" işaretle), (3) MIDI'lerini `estimate_mode_v3`'ten geçir,
    (4) doğruluk + confusion matrix raporla.
  - Gereken: ~1 gün iş; yeni bağımlılık yok.

- [ ] **Batı tarafı için bağımsız benchmark: GiantSteps Key + Isophonics**
  - Ne: GiantSteps Key (604 parça, key etiketli — EDM ağırlıklı, tür farkına dikkat) ve
    Isophonics/Beatles anotasyonları (akor + key, pop/rock — bizim veri setine daha yakın).
  - Nasıl: ses dosyaları üzerinden fast_analyzer ile key tahmini → etiketle karşılaştır.
  - Gereken: veri setlerini indirme + küçük eval scripti.

- [ ] **Sabit değerlendirme protokolü (eval scripti)**
  - Ne: `tools/eval.py` — her matematik değişikliğinden sonra çalıştırılan tek komut.
  - Metrik: MIREX weighted key score (tam doğru=1.0, beşli komşu=0.5,
    relative=0.3, parallel=0.2) + mod bazında confusion matrix.
  - Neden: "değişiklik → ölç → tut/geri al" döngüsünü standartlaştırır
    (Harmonic Minor düzeltmesi tuttu, ilk tie-break denemesi bu sayede geri alındı).

- [ ] **Klasik ML önce (CRNN'den önce): feature-based sınıflandırıcı**
  - Ne: Random Forest / Gradient Boosting; öznitelikler = 12-dim ortalama chroma +
    akor geçiş istatistikleri (Markov satır özetleri) + tempo + akor çeşitliliği.
  - Eğitim verisi: YALNIZCA SymbTr + GiantSteps/Isophonics (uzman etiketli).
  - Bizim 100 elle etiketli şarkı: eğitime KARIŞTIRILMAZ — saf test seti olarak kalır.
  - Ön koşul: eval protokolü hazır + kural tabanlı sistemin tavanı ölçülmüş olmalı.

- [ ] **CRNN (deep learning) — en son adım**
  - Ön koşullar: (1) >3000 UZMAN etiketli örnek (SymbTr + Batı benchmarkları toplamı),
    (2) klasik ML denenmiş ve tavana dayanmış, (3) eval altyapısı oturmuş.
  - Bu koşullar sağlanmadan CRNN'e başlamak = gürültü ezberleyen model.

- [ ] **Veri çarkı (data flywheel): kullanıcı düzeltmeleri**
  - Ne: Streamlit arayüzüne "Tahmin doğru mu? [Evet/Hayır → doğrusu ne?]" düğmesi.
  - Düzeltmeler `songs.ground_truth_label` kolonuna yazılır → bağımsız etiket seti
    kullanıcı kullandıkça büyür.
  - Gereken: app.py'ye küçük form + mevcut `db_set_ground_truth` fonksiyonu (hazır).

- [ ] **Kalibrasyon ≠ Eğitim ayrımını koru**
  - Profil katsayısı ayarlama (kalibrasyon) 40-100 etiketle yapılabilir ve yapılıyor.
  - Model EĞİTİMİ binlerce bağımsız etiket ister. İkisini karıştırma:
    100 şarkıyla model eğitmeye çalışmak overfitting garantisidir.

- [ ] **Diyatonik aile çözücüsü (relative major/minor + Dorian/Phrygian) — YENİDEN DENENECEK**
  - Durum: Temmuz 2026'da denendi, **regresyon verdi** (%28→%18, tonik %46→%34) ve geri alındı.
  - Analiz doğruydu: 100 şarkılık ground truth'ta tonik hatalarının %31'i (17 şarkı),
    Major/Minor/Dorian/Phrygian/Mixolydian/Lydian'ın AYNI 7 notayı paylaşmasından
    kaynaklanıyor (kroma bunları pitch-class seviyesinde ayırt edemiyor).
  - Uygulama kabaldı: 6 aday arasında "son akor" kanıtına +5 puan vermek, çoğu
    şarkıda düşük frekanslı (0-3) sayımları eziyordu — rastgele hangi aday son
    akorla eşleşiyorsa (genelde gerçek toniğin IV'ü, yani Lydian adayı) başka
    hiçbir destek olmadan kazanıyordu. Yani ilk tie-break denemesindeki
    "körlemesine oylama" hatası, bu sefer 2 değil 6 aday üzerinde tekrarlandı.
  - Yeniden denerken: son-akor bonusunu kaldır, yalnızca kümülatif tonik akor
    frekansına dayan; VEYA orijinal adayın kanıtı ~0 iken başka bir adayın
    belirgin (2x+) fazla kanıtı varsa değiştir gibi çok daha muhafazakâr bir
    eşik koy. Her denemeden sonra 100 şarkılık ground truth'ta ölç, tutmazsa
    hemen geri al (`git diff` ile karşılaştır, DB'ye yazmadan önce _tmp script
    ile doğrula — bu oturumda izlenen disiplin).
  - Kod: `modules/math_theory.py`'de fonksiyon tamamen kaldırıldı (yarım kod
    bırakılmadı); üç çağrı noktası (`midi_labeler.py`, `fast_analyzer.py`,
    `harmonai_pipeline.py`) önceki (tie_break_key + margin) haline döndü.

---

## Yeni Özellikler

- [ ] **İki şarkı karşılaştırma** — "Bu iki şarkı harmonik olarak %67 benzer" çıktısı
- [ ] **Markov akor önerici** — başlangıç akoru ver, olası devamları sırala (eğitim aracı)
- [ ] **DB üzerinden arama** — "Hicaz modundaki şarkıları göster" sorgu arayüzü
- [ ] **DB üzerinden JSONB dönüşümü** —  içeride JSON string var. Bunları JSONB'ye çevirmek
- [ ] **Supabase e verileri at** 


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

# HarmonAI - Sistem Bağlamı ve Yapay Zeka Yönergeleri

Merhaba Claude. Bu projede çalıştığın süre boyunca aşağıdaki mimari, teknoloji yığını ve kodlama standartlarına kesinlikle uymanı bekliyorum.

## 🎵 Proje Özeti (Project Overview)
**HarmonAI**, Türk makam müziği ile Batı tonal müziğini matematiksel ve istatistiksel olarak karşılaştıran, yapay zeka destekli bir armonik analiz ve veri mühendisliği sistemidir. Proje, yapılandırılmamış ses sinyallerini (YouTube/WAV/MIDI) alır, 12 boyutlu kroma vektörlerine dönüştürür, 108 sınıflı akor şablonlarıyla eşleştirir, Markov matrisleriyle analiz eder ve Gemini API üzerinden anlamsal müzikolojik raporlar üretir. Streamlit arayüzü (`app.py`) üzerinden hızlı (librosa, ~10sn) veya tam (Basic Pitch CNN → MIDI, ~2-3dk) analiz modu seçilebilir.

## 🏗️ Sistem Mimarisi (Core Architecture)
Sistem temel olarak 7 katmandan oluşur:
1. **Veri Girişi & Ön İşleme:** YouTube indirme (yt-dlp) veya MIDI yükleme, perküsyon kanalının (davulların) filtrelenmesi.
2. **Kroma Özellik Çıkarımı:** STFT ile 12 boyutlu kroma vektörlerinin oluşturulması (`librosa` / `pretty_midi`).
3. **Akor Sınıflandırma:** 108 sınıflı (12 kök x 9 tür) akor sözlüğü, Kosinüs Benzerliği ve Bayesyen bağlam bonusu (+0.15) kullanılarak akor tespiti.
4. **Ton/Makam Tespiti:** Hicaz ve Kürdi gibi Türk makamlarını içeren 9 özel Tonal Hiyerarşi profili ile Pearson korelasyonu (Z12 döngüsel kaydırma); ilk iki aday çok yakınsa nötr akor dizisi kanıtlarıyla tie-break (Locrian, yanlış pozitif ürettiği için Temmuz 2026'da çıkarıldı).
5. **Markov Modellemesi:** 1. dereceden 108x108 Markov geçiş matrislerinin oluşturulması (`modules/markov_models.py`).
6. **Veri Zenginleştirme & Etiketleme:** Web scraping (DuckDuckGo, Selenium, BeautifulSoup) ile tab sitelerinden çapraz doğrulama; `modules/midi_labeler.py` ile otomatik key/mode etiketleme; `modules/ground_truth_tool.py` ile kör (blind) elle doğrulama ve doğruluk ölçümü. (NOT: Spotify audio-features API Kasım 2024'te yeni uygulamalara kapatıldı — `spotify_labeler.py` kullanım dışı, yalnızca referans.)
7. **LLM Raporlama:** Gemini 2.5 Flash API kullanılarak sayısal verilerin akademik bir müzikoloji raporuna dönüştürülmesi; veri seti şarkı listeleri Groq (llama-3.3-70b) ile üretilir.

## 🛠️ Teknoloji Yığını (Tech Stack)
- **Dil:** Python 3.10+
- **Sinyal İşleme & Müzik:** `librosa`, `pretty_midi`, `basic-pitch` (CNN, TensorFlow), `numpy`, `scipy`
- **Veri & Görselleştirme:** `pandas`, `matplotlib`, `seaborn`
- **Veri Madenciliği (Scraping):** `selenium`, `beautifulsoup4`, `requests`, `yt-dlp`, `re` (Regex)
- **API Entegrasyonları:** `google-genai` (Gemini raporlama), `groq` (şarkı listesi üretimi)
- **Veritabanı & Çevre:** PostgreSQL (`psycopg2`; yerel `harmonai` DB veya `supabase_password` tanımlıysa Supabase), `python-dotenv`
- **UI & Otomasyon:** `streamlit` (app.py), `schedule` (auto_builder)
- **Test:** `pytest` (`tests/` klasörü — `python -m pytest tests/ -v`)

## 📂 Dizin Yapısı (Directory Structure)
- `app.py`: Streamlit arayüzü (analiz giriş noktası).
- `harmonai_pipeline.py`: Async ana pipeline — fast (librosa) ve full (Basic Pitch) modları.
- `dataset_builder.py`: Groq → YouTube → MIDI toplu veri seti oluşturucu.
- `modules/`: Tüm çekirdek modüller —
  - `math_theory.py`: Akor sözlükleri, tonal hiyerarşi profilleri (PROFILES_V3) ve matematiksel formüller.
  - `audio_core.py`: YouTube indirme, Basic Pitch dönüşümü, davul temizleme, tempo.
  - `fast_analyzer.py`: MIDI'siz hızlı librosa analizi.
  - `web_scraper.py`: Akor sitelerinden tab kazıma (TR + EN siteler).
  - `llm_agent.py`: Gemini promptları ve rapor üretimi.
  - `db_manager.py`: PostgreSQL bağlantısı ve tüm DB işlemleri (songs + analyses tabloları).
  - `midi_labeler.py`: MIDI dosyalarından otomatik key/mode etiketleme.
  - `ground_truth_tool.py`: Elle doğrulama CSV export/import + doğruluk raporu.
  - `auto_builder.py`: dataset_builder'ı periyodik çalıştıran zamanlayıcı.
  - `markov_models.py`: Markov geçiş matrisleri ve kültürlerarası delta analizi.
  - `spotify_labeler.py`: ⚠️ Kullanım dışı (Spotify API kısıtlaması) — referans.
- `veri_seti/`: Ham MIDI (.mid) dosyaları (Örn: `Sanatçı-Şarkı_davulsuz.mid`) — gitignore'lu.
- `tests/`: pytest birim testleri (math_theory, web_scraper parse).
- `ground_truth_worksheet.csv`: Elle etiketleme çalışma dosyası.
- `.env`: API anahtarları ve DB şifresi (GEMINI_API_KEY, GROQ_API_KEY, database_password / supabase_password) — asla commit edilmez.

## 🧑‍💻 Kodlama Kuralları ve Geliştirici Standartları (Coding Standards)
Lütfen kod yazarken veya revize ederken şu kurallara dikkat et:
1. **Modülerlik:** Spagetti kod yazma. Her işlemi (örneğin dosya okuma, API isteği yapma, veritabanına yazma) ayrı fonksiyonlar (veya class'lar) halinde tasarla.
2. **Hata Yönetimi (Error Handling):** API çağrılarında (Gemini, Groq) ve Web Scraping işlemlerinde `try-except` bloklarını zorunlu kıl; hatayı ASLA sessizce yutma — en az hata sınıfı ve kısa mesajla logla. Rate Limit (429) durumları için `time.sleep()` veya retry mekanizmaları ekle.
3. **Regex ve Metin Temizleme:** Kullanıcı veya internet kaynaklı metinlerdeki (dosya adları, HTML etiketleri) Türkçe karakterleri ve gereksiz boşlukları (strip) her zaman temizle.
4. **Matematiksel Sadakat:** Müzik teorisi hesaplamalarında (Kroma, Markov, TVD, Cosine Similarity) `numpy`'ın vektörel işlemlerini (vectorization) kullanarak performansı optimize et. For döngüleriyle matris hesaplamaktan kaçın. Tonal profil değerlerini değiştirirken mutlaka `tests/` regresyon testlerini ve 40+ şarkılık ground truth doğruluğunu kontrol et.
5. **Loglama ve Çıktılar:** Ekrana devasa hata yığınları (stack trace) veya uzun listeler basma. İnsan tarafından okunabilir, temiz ve özet `print` f-string logları kullan (Örn: `[BAŞARILI] Duman - Halil İbrahim Sofrası işlendi.`).
6. **Güvenlik:** Hiçbir koşulda koda API anahtarı veya şifre hardcode etme. Her zaman `os.getenv()` + `.env` kullan; hata mesajlarında bile kullanıcıyı anahtarı koda yazmaya yönlendirme.
7. **Doğrulama:** Davranış değiştiren her düzeltmeden sonra `python -m pytest tests/ -v` çalıştır; ton tespiti matematiğine dokunduysan ground truth doğruluğunu (`ground_truth_tool.py --import-csv`) yeniden ölç.

## 🎯 Mevcut Odak (Current Focus)
Akademik çekirdek matematik tamamlandı; veri seti ~1930 şarkıya ulaştı. Şu anki odak **doğrulama ve kalibrasyon**: elle etiketlenmiş ground truth setini (hedef 100 şarkı) büyütmek, ton/mod tespit doğruluğunu (mevcut taban çizgisi: %35, 40 şarkı üzerinde) profil kalibrasyonuyla yükseltmek ve Streamlit arayüzünü deploy etmek. Büyük model işleri (2. derece Markov, CRNN) veri doğruluğu kanıtlanana kadar donduruldu. Bilinen açık konu: relative major/minor ayrımı (kroma tabanlı yöntemin yapısal sınırı) — akor dizisi tabanlı önyargısız tie-breaker ayrı bir oturumda denenecek.

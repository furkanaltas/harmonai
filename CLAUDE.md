# HarmonAI - Sistem Bağlamı ve Yapay Zeka Yönergeleri

Merhaba Claude. Bu projede çalıştığın süre boyunca aşağıdaki mimari, teknoloji yığını ve kodlama standartlarına kesinlikle uymanı bekliyorum.

## 🎵 Proje Özeti (Project Overview)
**HarmonAI**, Türk makam müziği ile Batı tonal müziğini matematiksel ve istatistiksel olarak karşılaştıran, yapay zeka destekli bir armonik analiz ve veri mühendisliği sistemidir. Proje, yapılandırılmamış ses sinyallerini (MIDI/Audio) alır, 12 boyutlu kroma vektörlerine dönüştürür, 108 sınıflı akor şablonlarıyla eşleştirir, Markov matrisleriyle analiz eder ve Gemini API üzerinden anlamsal müzikolojik raporlar üretir.

## 🏗️ Sistem Mimarisi (Core Architecture)
Sistem temel olarak 7 katmandan oluşur:
1. **Veri Girişi & Ön İşleme:** MIDI dosyalarının yüklenmesi, perküsyon kanalının (davulların) filtrelenmesi.
2. **Kroma Özellik Çıkarımı:** STFT ile 12 boyutlu kroma vektörlerinin oluşturulması (`librosa`).
3. **Akor Sınıflandırma:** 108 sınıflı (12 kök x 9 tür) akor sözlüğü, Kosinüs Benzerliği ve Bayesyen bağlam bonusu (+0.15) kullanılarak akor tespiti.
4. **Ton/Makam Tespiti:** Hicaz ve Kürdi gibi Türk makamlarını içeren 10 özel Tonal Hiyerarşi profili ile Pearson korelasyonu kullanılarak (Z12 döngüsel kaydırma / tonal normalizasyon) ton tespiti.
5. **Markov Modellemesi:** 1. dereceden 108x108 Markov geçiş matrislerinin oluşturulması.
6. **Veri Zenginleştirme (Data Pipeline):** Web scraping (DuckDuckGo, Selenium, BeautifulSoup) ile tab sitelerinden çapraz doğrulama verisi çekilmesi ve Spotify API ile ton/mod etiketlemesi.
7. **LLM Raporlama:** Gemini 2.5 Flash API kullanılarak sayısal verilerin akademik bir müzikoloji raporuna dönüştürülmesi.

## 🛠️ Teknoloji Yığını (Tech Stack)
- **Dil:** Python 3.10+
- **Sinyal İşleme & Müzik:** `librosa`, `pretty_midi`, `numpy`, `scipy`
- **Makine Öğrenmesi:** `scikit-learn` (Random Forest, Markov)
- **Veri Madenciliği (Scraping):** `selenium`, `beautifulsoup4`, `requests`, `re` (Regex)
- **API Entegrasyonları:** `google-genai` (Gemini), `spotipy` (Spotify API)
- **Veritabanı & Çevre:** `sqlite3` (dataset.db), `python-dotenv`

## 📂 Dizin Yapısı (Directory Structure)
- `veri_seti/`: Ham MIDI (.mid) dosyalarının bulunduğu klasör (Örn: `Sanatçı-Şarkı_davulsuz.mid`).
- `dataset.db`: Şarkıların etiketlerini (Spotify Key/Mode vb.) tutan SQLite veritabanı.
- `math_theory.py`: Akor sözlükleri, tonal hiyerarşi katsayıları (alfa, beta, gama) ve matematiksel formüllerin tutulduğu modül.
- `llm_agent.py`: Gemini promptlarının ve LLM entegrasyonunun bulunduğu modül.
- `spotify_labeler.py`: Spotify API veri çekme ve etiketleme betiği. (Henüz aktif değil)
- `.env`: API anahtarlarının (Gemini, Spotify) bulunduğu gizli dosya.

## 🧑‍💻 Kodlama Kuralları ve Geliştirici Standartları (Coding Standards)
Lütfen kod yazarken veya revize ederken şu kurallara dikkat et:
1. **Modülerlik:** Spagetti kod yazma. Her işlemi (örneğin dosya okuma, API isteği yapma, veritabanına yazma) ayrı fonksiyonlar (veya class'lar) halinde tasarla.
2. **Hata Yönetimi (Error Handling):** API çağrılarında (Spotify, Gemini) ve Web Scraping işlemlerinde `try-except` bloklarını zorunlu kıl. Rate Limit (429) durumları için `time.sleep()` veya retry mekanizmaları ekle.
3. **Regex ve Metin Temizleme:** Kullanıcı veya internet kaynaklı metinlerdeki (dosya adları, HTML etiketleri) Türkçe karakterleri ve gereksiz boşlukları (strip) her zaman temizle.
4. **Matematiksel Sadakat:** Müzik teorisi hesaplamalarında (Kroma, Markov, TVD, Cosine Similarity) `numpy`'ın vektörel işlemlerini (vectorization) kullanarak performansı optimize et. For döngüleriyle matris hesaplamaktan kaçın.
5. **Loglama ve Çıktılar:** Ekrana devasa hata yığınları (stack trace) veya uzun listeler basma. İnsan tarafından okunabilir, temiz ve özet `print` f-string logları kullan (Örn: `[BAŞARILI] Duman - Halil İbrahim Sofrası işlendi.`).
6. **Güvenlik:** Hiçbir koşulda koda API anahtarı hardcode etme. Her zaman `os.getenv()` kullan.

## 🎯 Mevcut Odak (Current Focus)
Sistemin akademik çekirdek matematik hesaplamaları tamamlandı. Şu anki geliştirme odağı sistemi otomatize etmek, veri mühendisliği boru hattını (Data Pipeline) kusursuzlaştırmak ve Spotify gibi dış API'ler ile `dataset.db` üzerinde sağlam bir "Ground Truth" veri seti oluşturmaktır.
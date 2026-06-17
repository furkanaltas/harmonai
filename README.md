# 🎵 HarmonAI — AI-Powered Musical Harmony Analyzer

HarmonAI, bir şarkının YouTube linkinden yola çıkarak müzikal armoni analizini otomatik olarak yapan yapay zeka destekli bir sistemdir.

## Ne Yapar?

Bir YouTube linki, sanatçı adı ve şarkı adı girdiğinde HarmonAI:

- Şarkıyı indirir ve ses dosyasına dönüştürür
- **Paralel olarak** iki bağımsız analiz başlatır:
  - **Thread 1 — Ses Analizi:** Şarkıyı MIDI formatına çevirir, davul/perküsyon kanallarını temizler, matematiksel yöntemlerle ton, mod ve akor dizisini çıkarır
  - **Thread 2 — Web Scraping:** Şarkının akorlarını web üzerinden çeker
- Her iki kaynaktan gelen veriyi birleştirerek Google Gemini ile kapsamlı bir armoni raporu üretir

## Teknik Mimari

```
[YouTube URL]
      │
      ▼
[Ses İndirme]  ──────────────────────────────┐
      │                                       │
      ├──► [Thread 1: MIDI Dönüşüm]          │
      │         │                             │
      │    [Davul Temizleme]                  │
      │         │                             │
      │    [Ton / Mod / Akor Analizi]         │
      │                                       │
      └──► [Thread 2: Web Scraping]           │
                │                             │
           [Akor Verisi]                      │
                │                             │
                └──────────────┬──────────────┘
                               ▼
                        [LLM Raporu]
                      (Google Gemini)
```

**Neden ThreadPoolExecutor?**
- Web scraping I/O bound (ağ gecikmesi bekleniyor) → thread idealdir
- Basic Pitch inference sırasında TensorFlow GIL'i serbest bırakır → paralel çalışmaya izin verir
- İki işlemin toplam süresi, ikisinden uzun olanınki kadardır — tipik kazanç ~40-60 saniye

## Kullanılan Teknolojiler

| Alan | Kütüphane |
|---|---|
| Ses indirme | `yt-dlp` |
| Ses analizi | `librosa`, `basic-pitch` |
| MIDI işleme | `pretty_midi` |
| Web scraping | `BeautifulSoup`, `Selenium`, `requests` |
| ML / Matematik | `numpy`, `scipy` |
| LLM entegrasyonu | `google-genai` (Gemini) |
| Arayüz | `Streamlit` |

## Kurulum

```bash
# Repoyu klonla
git clone https://github.com/furkanaltas/harmonai.git
cd harmonai

# Bağımlılıkları yükle
pip install -r requirements.txt

# API key'ini ayarla
cp .env.example .env
# .env dosyasını aç ve GEMINI_API_KEY değerini gir
```

## Çalıştırma

```bash
streamlit run app.py
```

Tarayıcıda arayüz açılır. YouTube linki, sanatçı adı ve şarkı adını gir, analiz başlar.

> ⚠️ Analiz işlemi şarkı uzunluğuna bağlı olarak **2-4 dakika** sürebilir.

## Çıktı Örneği

```
Ton       : A Minor
Tempo     : 124 BPM
Akorlar   : Am · F · C · G · Em · Dm
Web Akorları : Am · F · C · G

--- HarmonAI Raporu ---
Bu şarkı La minör tonalitesinde yazılmış olup...
```

## Proje Yapısı

```
harmonai/
├── app.py                  # Streamlit arayüzü
├── harmonai_pipeline.py    # Ana pipeline (async)
├── modules/
│   ├── audio_core.py       # Ses indirme, MIDI dönüşüm
│   ├── math_theory.py      # Ton, mod, akor analizi
│   ├── web_scraper.py      # Web'den akor çekme
│   └── llm_agent.py        # Gemini LLM entegrasyonu
├── requirements.txt
├── .env.example
└── .gitignore
```

## Geliştirici

**Furkan Altaş** — Ege Üniversitesi Matematik Bölümü  
Bitirme tezi projesi · 2026

---

*HarmonAI, müzik teorisi ile yapay zekayı birleştirerek şarkıların armonik yapısını matematiksel yöntemlerle analiz eder.*

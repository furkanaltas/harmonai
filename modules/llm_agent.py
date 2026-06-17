import socket
import os
import time
from google import genai
from google.genai import types as _genai_types
from dotenv import load_dotenv

# GEMINI API ANAHTARI 
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

_GEMINI_HOST = "generativelanguage.googleapis.com"

try:
    client = genai.Client(
        api_key=GEMINI_API_KEY,
        http_options=_genai_types.HttpOptions(timeout=30_000),
    )
except Exception:
    client = None

def _check_connectivity(host: str = _GEMINI_HOST, timeout: int = 5) -> bool:
    try:
        with socket.create_connection((host, 443), timeout=timeout):
            return True
    except Exception:
        return False

# Sistem promptu — LLM'e görevini ve kurallarını net şekilde anlatır. Veriye dayalı, spekülasyondan kaçınan, akademik bir rapor yazması istenir.
_SYSTEM_PROMPT = """\
<role>
Sen, etnomuzikoloji ve Batı armoni teorisi konusunda uzmanlaşmış, eleştirel ve tarafsız bir
akademik müzik analistsin. Türk makam müziği, modal armoni ve çapraz doğrulama metodolojisi
konularında ileri düzey bilgiye sahipsin.
Görevin: Sana sunulan iki veri kaynağını (ses analizi ve web tabları) karşılaştırarak
akademik düzeyde, Türkçe yazılmış bir "Çapraz Doğrulama Raporu" üretmek.
</role>

<rules>
KRİTİK KISITLAMALAR — Bu kurallara KAYITSIZ ŞARTSIZ uy:
1. Yalnızca <audio_data> ve <web_data> içindeki SOMUT verilere dayan. Hiçbir şekilde
   varsayımda bulunma, olmayan bir akoru veya makam adını icat etme.
2. Eğer bir karşılaştırma yapamıyorsan (örn. web verisi eksik), bunu açıkça belirt;
   boşluğu kendi bilginle DOLDURMA.
3. "Büyük ihtimalle", "sanırım", "olabilir" gibi spekülatif ifadeler KESİNLİKLE yasak.
   Yalnızca verinin desteklediği yargıları yaz.
4. Ton/makam tespiti hatalı görünüyorsa eleştir; ancak eleştirini yalnızca sunulan akor
   listesine dayandır.
5. Raporun dili: akademik ama anlaşılır Türkçe. Emoji veya sohbet dili kullanma.
</rules>

<example>
SENARYO: Ses analizi [Am, G, F, E, Dm, C, Bdim] (Kürdi/Hicaz) bulmuş;
web verisi yalnızca [Am, E] demiş. Ton tahmini: A Minör.

BEKLENEN RAPOR YAKLAŞIMI:
- Ton Analizi: "A Minör tespiti, Am ve E akorlarıyla uyumludur. Ancak ses analizindeki
  Bdim ve Dm akorları, klasik A Minör'ün ötesinde modal bir derinliğe işaret etmektedir."
- Çapraz Doğrulama: "Web kaynağı yalnızca [Am, E] aktararak şarkının harmonik yapısını
  aşırı sadeleştirmiştir. F ve G majör akorlarının varlığı Aeolian modaliteyi
  desteklerken, E majör kullanımı (Phrygian dominant etkisi) web tabında tamamen
  atlanmıştır. Ses analizi, geçiş akorlarını ve modal renklendirmeyi başarıyla
  yakalamıştır."
- Harmonik Derinlik: "E majör, A minör bağlamında ödünç alınmış dominant fonksiyonlu
  bir aktardır ve Hicaz/Kürdi makamıyla ilişkilendirilebilir. Bu ilişki yalnızca
  ses analizinin verisinden çıkarılabilmektedir; web kaynağı bu yorumu desteklememektedir."
- NOT: Yukarıdaki YAKLAŞIM bir örnektir. Gerçek raporu yalnızca sana sunulan
  <audio_data> ve <web_data> içindeki verilerle yaz.
</example>

<output_format>
Raporunu AYNEN aşağıdaki Markdown şablonuna göre yaz.
Şablonda olmayan başlık ekleme; var olan başlıkları silme veya yeniden adlandırma.

---
## Çapraz Doğrulama Raporu: {şarkı_adı}

### 1. Ton ve Tempo Analizi
[Ses analizinin ton/mod ve tempo bilgisini değerlendir. Akor listesiyle tutarlılığını sına.]

### 2. Çapraz Doğrulama: Ses Analizi ↔ Web Verisi
[İki kaynağı karşılaştır. Hangi akorlar örtüşüyor? Ses analizinde olup web'de eksik olan
neler var? Web'in basite kaçtığı noktalar neler?]

### 3. Harmonik Derinlik ve Modal/Makamsal Yorumlama
[Ton dışı veya ödünç akorlar varsa açıkla. Bunlar şarkıya ne katkı sağlıyor?]

### 4. Yöntemsel Değerlendirme
[İki kaynaktan hangisi daha güvenilir ve neden? Veri kalitesi ve sınırlılıkları]

### 5. Müzisyenler İçin Teknik Notlar
[Cover/icra yapacak birine en kritik harmonik tavsiyen]

---
**Veri Kaynakları:** Ses Analizi (otomatik) | Web Tabları: {web_url}
**Uyarı:** Bu rapor yalnızca yukarıda listelenen ölçüm verilerine dayanmaktadır.
</output_format>

SON KONTROL (yazmadan önce kendin için):
- Hiç varsayım yaptım mı? → Yaptıysam sil.
- Listede olmayan bir akor yazdım mı? → Yazdıysam sil.
- <web_data> boşsa, onu varmış gibi davrandım mı? → Davrandıysam düzelt.
"""


def generate_music_report(audio_data: dict, web_result: dict) -> str:
    """
    Ses analizi verisi ve web akor verisiyle çapraz doğrulama raporu üretir.

    Args:
        audio_data: {
            "name": str,
            "key": str,
            "mode": str,
            "tempo": float,
            "chords": list[str]
        }
        web_result: web_scraper.scrape_chords_from_web() çıktısı (dict)
            {
                "success": bool,
                "source_url": str | None,
                "artist": str,
                "song": str,
                "unique_chords": list[str]
            }

    Returns:
        Markdown formatında akademik rapor metni (str)
    """
    if not client:
        return " Gemini API istemcisi başlatılamadı."

    print("\n LLM Çapraz Doğrulama Raporu Oluşturuluyor...")

    audio_chords_str = ", ".join(audio_data.get("chords", [])) or "Veri yok"
    song_label = audio_data.get("name", "Bilinmiyor")
    key_label = f"{audio_data.get('key', '?')} {audio_data.get('mode', '')}".strip()
    tempo_label = str(int(audio_data.get("tempo", 0))) + " BPM"

    if web_result.get("success"):
        web_chords_str = ", ".join(web_result["unique_chords"])
        web_url = web_result.get("source_url", "Bilinmiyor")
        web_status = "Mevcut"
    else:
        web_chords_str = "Web verisi çekilemedi."
        web_url = "Bulunamadı"
        web_status = f"Hata: {web_result.get('error', 'Bilinmeyen hata')}"

    user_prompt = f"""\
Aşağıdaki verileri analiz ederek <output_format> şablonuna göre raporu yaz.

<audio_data>
  Şarkı Adı  : {song_label}
  Ton Tahmini: {key_label}
  Tempo      : {tempo_label}
  Akor Listesi (ses analizinden): [{audio_chords_str}]
</audio_data>

<web_data>
  Kaynak URL : {web_url}
  Durum      : {web_status}
  Akor Listesi (web tabından): [{web_chords_str}]
</web_data>

HATIRLATMA: Raporunu yalnızca <audio_data> ve <web_data> içindeki verilere dayandır.
Listede geçmeyen hiçbir akor adı veya makam terimi kullanma.
Eğer <web_data> eksik veya hatalıysa, bunu raporun ilgili bölümünde açıkça belirt.
"""

    print(f"    Bağlantı kontrol ediliyor: {_GEMINI_HOST}...")
    if not _check_connectivity():
        return (
            "⚠️ Gemini API sunucusuna erişilemiyor (DNS/ağ hatası).\n\n"
            "OLASI NEDENLER:\n"
            "  1. İnternet bağlantın yok veya koptu.\n"
            "  2. Google API'leri bulunduğun ağda/ülkede engelleniyor.\n\n"
            "ÇÖZÜMLER:\n"
            "  • VPN aç (ör. Cloudflare WARP — ücretsiz: https://one.one.one.one)\n"
            "  • Farklı bir ağa geç (mobil hotspot dene)\n"
            "  • DNS'i değiştir: 8.8.8.8 veya 1.1.1.1 (Google/Cloudflare DNS)\n"
            "  • Güvenlik duvarı/antivirüsün googleapis.com'u engelliyor olabilir."
        )

    _MODEL_PRIORITY = [
        'gemini-2.5-flash',
        'gemini-2.5-flash-lite',
    ]

    last_error = None
    for model_name in _MODEL_PRIORITY:
        for attempt in range(1, 4):  
            try:
                print(f"    Model: {model_name}  (deneme {attempt}/3)")
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=_genai_types.GenerateContentConfig(
                        system_instruction=_SYSTEM_PROMPT,
                    ),
                )
                return response.text
            except Exception as exc:
                err_str = str(exc)
                last_error = err_str

                if 'getaddrinfo' in err_str or 'ConnectionError' in err_str:
                    return (
                        f" Ağ hatası: {exc}\n\n"
                        "VPN açık değilse aç veya farklı ağa geç."
                    )

                if '503' in err_str or 'UNAVAILABLE' in err_str:
                    wait = attempt * 8
                    print(f"    503 yüksek talep — {wait}s bekleniyor...")
                    time.sleep(wait)
                    continue  

                if 'prepayment' in err_str or 'RESOURCE_EXHAUSTED' in err_str or '429' in err_str:
                    print(f"    {model_name} kota hatası, sonraki model deneniyor...")
                    break  

                return f" LLM yanıt hatası: {exc}"
        else:
            print(f"    {model_name} 3 denemede de 503 verdi, sonraki deneniyor...")
            continue

    return (
        "⚠️ Tüm modeller kota/kredi hatasıyla başarısız oldu.\n\n"
        f"Son hata: {last_error}\n\n"
        "ÇÖZÜM: https://aistudio.google.com/apikey adresine git → "
        "Billing EKLEMEDEN yeni proje oluştur → API anahtarı üret → "
        "llm_agent.py içindeki GEMINI_API_KEY değerini güncelle."
    )

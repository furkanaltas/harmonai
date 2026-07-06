import os
import re
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup

PREFERRED_BROWSER: str = 'chrome'
_BROWSER_FALLBACK_ORDER: list[str] = ['requests', 'chrome', 'firefox', 'opera']

_ROOTS = [
    'C#', 'Db', 'D#', 'Eb', 'F#', 'Gb', 'G#', 'Ab', 'A#', 'Bb',
    'C', 'D', 'E', 'F', 'G', 'A', 'B'
]
_SUFFIXES = ['maj7', 'maj', 'm7', 'dim', 'aug', 'sus4', 'sus2', 'm', '7', '9', '5', '']
_VALID_CHORDS: set[str] = {r + s for r in _ROOTS for s in _SUFFIXES}

# Tek harfli akorlar çok gürültülü — sadece bracket içinde ([C]) ya da
# yüksek yoğunluk bölgesinde (akor satırı) kabul edilir.
_SINGLE_LETTER_NOISE = {'A', 'B', 'C', 'D', 'E', 'F', 'G'}

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    )
}

_TURKISH_SITES = [
    "repertuarim.com",
    "akormerkezi.com",
    "akor.alternatifim.com",
    "akorlar.com",
]
_WESTERN_SITES = [
    "ultimate-guitar.com",
    "chordu.com",
    "e-chords.com",
    "chordify.net",
]
_OPERA_PATHS = [
    r'C:\Users\Asus\AppData\Local\Programs\Opera\opera.exe',
    r'C:\Program Files\Opera\opera.exe',
    r'C:\Program Files (x86)\Opera\opera.exe',
]

# Akor regex desenleri:
# 1. Bracket format: [Am], [F#m7], [Csus4]  ← tab sitelerinde en yaygın
# 2. Satır-başı format: "Am  F  C  G" gibi yalnızca akorlardan oluşan satırlar
_RE_BRACKET = re.compile(
    r'\[([A-G][#b]?(?:maj7|maj|m7|dim|aug|sus4|sus2|m|7|9|5)?)\]'
)
_RE_WORD = re.compile(
    r'(?<!\w)([A-G][#b]?(?:maj7|maj|m7|dim|aug|sus4|sus2|m|7|9|5)?)(?!\w)'
)


# ── Selenium WebDriver ────────────────────────────────────────────────────────

def _get_webdriver(browser: str):
    try:
        from selenium import webdriver

        if browser == 'chrome':
            from selenium.webdriver.chrome.options import Options
            opts = Options()
            opts.add_argument('--headless=new')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            opts.add_argument('--disable-blink-features=AutomationControlled')
            opts.add_experimental_option('excludeSwitches', ['enable-automation'])
            opts.add_experimental_option('useAutomationExtension', False)
            return webdriver.Chrome(options=opts)

        elif browser == 'firefox':
            from selenium.webdriver.firefox.options import Options
            opts = Options()
            opts.add_argument('--headless')
            return webdriver.Firefox(options=opts)

        elif browser == 'opera':
            from selenium.webdriver.chrome.options import Options
            opts = Options()
            for path in _OPERA_PATHS:
                if os.path.exists(path):
                    opts.binary_location = path
                    break
            else:
                return None
            opts.add_argument('--headless=new')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            return webdriver.Chrome(options=opts)

    except Exception as e:
        print(f"    [webdriver:{browser}] başlatılamadı — {type(e).__name__}: {str(e).splitlines()[0][:120]}")
        return None


# ── URL Arama ─────────────────────────────────────────────────────────────────

def _search_url_via_browser(query: str, browser: str, sites: list[str]) -> str | None:
    driver = _get_webdriver(browser)
    if driver is None:
        return None
    try:
        search_url = 'https://duckduckgo.com/?q=' + urllib.parse.quote(query) + '&ia=web'
        driver.get(search_url)
        time.sleep(2.5)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            if 'duckduckgo.com' in href or not href.startswith('http'):
                continue
            if any(site in href for site in sites):
                return href
        return None
    except Exception as e:
        print(f"    [ddg:selenium] arama hatası — {type(e).__name__}: {str(e).splitlines()[0][:120]}")
        return None
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _extract_url_from_ddg(soup: BeautifulSoup, sites: list[str]) -> str | None:
    for a in soup.find_all('a', class_='result__url'):
        link = a.get('href', '')
        if any(site in link for site in sites):
            if "uddg=" in link:
                return urllib.parse.unquote(link.split("uddg=")[1].split("&")[0])
            return f"https://{link.strip()}" if not link.startswith('http') else link
    return None


def _search_url_via_requests(query: str, sites: list[str]) -> str | None:
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        res = requests.get(ddg_url, headers=_HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        return _extract_url_from_ddg(soup, sites)
    except Exception as e:
        print(f"    [ddg:requests] arama hatası — {type(e).__name__}: {str(e).splitlines()[0][:120]}")
        return None


# ── Sayfa İçeriği Çekme ───────────────────────────────────────────────────────

def _fetch_html(url: str, use_browser: bool = False) -> str | None:
    """
    HTML içeriğini çeker.
    use_browser=True → Selenium ile render eder (JS bağımlı siteler için).
    use_browser=False → requests ile hızlı çeker.
    """
    if use_browser:
        driver = _get_webdriver(PREFERRED_BROWSER)
        if driver:
            try:
                driver.get(url)
                time.sleep(3)  # JS render için bekle
                return driver.page_source
            except Exception as e:
                print(f"    [fetch:selenium] {url[:60]} — {type(e).__name__}: {str(e).splitlines()[0][:120]}")
                return None
            finally:
                try:
                    driver.quit()
                except Exception:
                    pass

    try:
        res = requests.get(url, headers=_HEADERS, timeout=12)
        res.raise_for_status()
        return res.text
    except Exception as e:
        print(f"    [fetch:requests] {url[:60]} — {type(e).__name__}: {str(e).splitlines()[0][:120]}")
        return None


# ── Site-Specific Content Extraction ─────────────────────────────────────────

def _extract_content_area(soup: BeautifulSoup, url: str) -> str:
    """
    Sayfanın akor içeriğini taşıyan bölümünü döndürür.

    Her site farklı HTML yapısı kullanır. Önce bilinen site'e özgü seçiciler
    denenir; bulunamazsa genel "yüksek akor yoğunluğu" buluşsal yöntemi devreye girer.

    Neden site-specific seçici gerekli:
      - Nav/footer/sidebar çok gürültü üretir
      - İlgili şarkı listeleri rastgele akor adları içerebilir
      - Yorum bölümü "Am" gibi kısaltmalar içerebilir
    """

    # Nav/header/footer/script gibi gürültü kaynaklarını önceden temizle
    for tag in soup.find_all(['nav', 'header', 'footer', 'script', 'style', 'aside']):
        tag.decompose()

    # ── Site'e özgü seçiciler ───────────────────────────────────────────────

    if 'repertuarim.com' in url:
        # Akorlar genellikle <pre> veya class içeren div'lerde
        for selector in ['.song-content', '.chord-content', 'pre', '.tab']:
            found = soup.select_one(selector)
            if found:
                return found.get_text(separator='\n')

    elif 'akormerkezi.com' in url or 'akorlar.com' in url:
        for selector in ['.chord-area', '.tab-content', 'pre', '#content', '.content']:
            found = soup.select_one(selector)
            if found:
                return found.get_text(separator='\n')

    elif 'akor.alternatifim.com' in url:
        for selector in ['pre', '.tab-content', '.chords', '#songtext']:
            found = soup.select_one(selector)
            if found:
                return found.get_text(separator='\n')

    elif 'ultimate-guitar.com' in url:
        # UG'nin akorları <pre> veya data-content attribute içinde
        pre = soup.find('pre')
        if pre:
            return pre.get_text(separator='\n')
        # JSON içinde de olabilir (js-store)
        store = soup.find(class_='js-store')
        if store and store.get('data-content'):
            return store['data-content']

    elif 'chordu.com' in url or 'e-chords.com' in url or 'chordify.net' in url:
        for selector in ['pre', '.chord-sheet', '.chords', '#tab', '.tab', '.song-text']:
            found = soup.select_one(selector)
            if found:
                return found.get_text(separator='\n')

    # ── Genel fallback: tüm <pre> etiketleri ───────────────────────────────
    # Tab/akor siteleri içeriği çoğunlukla <pre> içinde tutar (monospace hizalama)
    pre_blocks = soup.find_all('pre')
    if pre_blocks:
        return '\n'.join(p.get_text() for p in pre_blocks)

    # ── Son çare: tüm sayfa metni ───────────────────────────────────────────
    return soup.get_text(separator='\n')


# ── Akor Ayıklama ─────────────────────────────────────────────────────────────

def _parse_chords(text: str) -> list[str]:
    """
    Ham metinden geçerli akorları çıkarır.

    İki aşamalı yaklaşım:
    1. Bracket format önce taranır: [Am], [F#m7] — en güvenilir kaynak
       çünkü bracket içindeki token kesinlikle akor amacıyla yazılmıştır.
    2. Bracket bulunamazsa "akor yoğun satır" taraması yapılır:
       Bir satırın %60'ından fazlası akor ise o satır akor satırıdır.
       Bu yöntem gürültüyü büyük ölçüde filtreler.
    """
    chords_in_order: list[str] = []
    seen: set[str] = set()

    def _add(chord: str) -> None:
        if chord in _VALID_CHORDS and chord not in seen:
            seen.add(chord)
            chords_in_order.append(chord)

    # Aşama 1: Bracket format — [Am], [C#m7] vb.
    bracket_hits = _RE_BRACKET.findall(text)
    for chord in bracket_hits:
        _add(chord)

    if chords_in_order:
        return chords_in_order  # Bracket bulunduysa güvenilir, dur

    # Aşama 2: Akor yoğun satır taraması
    # Her satırı kelimelerine böl; kelimelerin >=%60'ı geçerli akors ise
    # o satırı "akor satırı" say ve içindeki akorları al.
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) < 2:
            continue
        chord_tokens = [t for t in tokens if t in _VALID_CHORDS]
        if len(chord_tokens) / len(tokens) >= 0.6:
            for chord in chord_tokens:
                # Tek harfli akorları akor yoğun satırda kabul et
                _add(chord)

    if chords_in_order:
        return chords_in_order

    # Aşama 3: Genel regex — gürültülü ama son çare
    for chord in _RE_WORD.findall(text):
        if chord in _SINGLE_LETTER_NOISE:
            continue  # Tek harfli akorları genel taramada atla
        _add(chord)

    return chords_in_order


# ── Yardımcı ──────────────────────────────────────────────────────────────────

def _build_failure(artist: str, song: str, reason: str) -> dict:
    return {
        "success": False,
        "source_url": None,
        "artist": artist,
        "song": song,
        "unique_chords": [],
        "error": reason,
    }


# ── JS render gerektiren siteler ──────────────────────────────────────────────

_JS_SITES = {'ultimate-guitar.com', 'chordify.net'}


def _needs_browser_render(url: str) -> bool:
    return any(site in url for site in _JS_SITES)


# ── Ana Fonksiyon ─────────────────────────────────────────────────────────────

def scrape_chords_from_web(artist: str, song_name: str, language: str = "tr") -> dict:
    """
    Verilen sanatçı ve şarkı için internet üzerinden akor çeker.

    Arama sırası:
      1. PREFERRED_BROWSER (chrome) ile Selenium → DuckDuckGo
      2. firefox → opera → requests fallback

    Sayfa çekme:
      - JS render gerektiren siteler (ultimate-guitar, chordify): Selenium ile
      - Diğer siteler: requests ile (hızlı)

    Akor ayıklama önceliği:
      1. [Am] bracket notation
      2. Akor yoğun satır taraması
      3. Genel regex (son çare)

    Parametreler:
        artist    : Sanatçı adı
        song_name : Şarkı adı
        language  : "tr" veya "en"
    """
    print(f" Web akor araması: '{artist} - {song_name}' [dil={language}]...")

    if language == "en":
        active_sites = _WESTERN_SITES
        queries = [
            f"{artist} {song_name} chords ultimate-guitar",
            f"{artist} {song_name} guitar chords",
            f"{song_name} {artist} chords tabs",
        ]
    else:
        active_sites = _TURKISH_SITES
        queries = [
            f"{artist} {song_name} akor repertuarim",
            f"{artist} {song_name} akor akormerkezi",
            f"{artist} {song_name} akor",
        ]

    # Hız: önce hafif requests (~1sn) denenir; Selenium (~5-8sn tarayıcı açılışı)
    # yalnızca requests sonuç bulamazsa devreye girer.
    browser_order = ['requests', PREFERRED_BROWSER] + [
        b for b in _BROWSER_FALLBACK_ORDER if b not in ('requests', PREFERRED_BROWSER)
    ]

    found_url: str | None = None

    for query in queries:
        print(f"    Aranıyor: '{query}'")
        for browser in browser_order:
            if browser == 'requests':
                found_url = _search_url_via_requests(query, active_sites)
                if found_url:
                    print(f"    Requests ile bulundu.")
                    break
            else:
                found_url = _search_url_via_browser(query, browser, active_sites)
                if found_url:
                    print(f"    {browser.capitalize()} ile bulundu.")
                    break
        if found_url:
            break
        time.sleep(1)

    if not found_url:
        print("    Guvenilir akor sitesi bulunamadi.")
        return _build_failure(artist, song_name, "Güvenilir akor sitesi bulunamadı.")

    print(f"    Hedef: {found_url}")

    # JS render gerektiriyor mu?
    use_browser = _needs_browser_render(found_url)
    if use_browser:
        print(f"    JS render modu (Selenium)...")

    html = _fetch_html(found_url, use_browser=use_browser)

    # JS render başarısız olduysa requests ile tekrar dene
    if not html and use_browser:
        print(f"    Selenium başarısız, requests ile deneniyor...")
        html = _fetch_html(found_url, use_browser=False)

    if not html:
        return _build_failure(artist, song_name, "Sayfa içeriği alınamadı.")

    soup = BeautifulSoup(html, 'html.parser')
    content = _extract_content_area(soup, found_url)
    unique_chords = _parse_chords(content)

    if not unique_chords:
        return _build_failure(
            artist, song_name,
            f"Site bulundu ({found_url}) ancak akor ayıklanamadı."
        )

    print(f"    Bulunan akorlar: {unique_chords}")
    return {
        "success": True,
        "source_url": found_url,
        "artist": artist,
        "song": song_name,
        "unique_chords": unique_chords,
    }

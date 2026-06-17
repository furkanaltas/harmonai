import os
import re
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup

#Kullanılmak istenen tarayıcı seçilir ve eğer o tarayıcı çalışmazsa diğerleri sırayla denenir. En son olarak requests yöntemi denenir.

PREFERRED_BROWSER: str = 'chrome'
_BROWSER_FALLBACK_ORDER: list[str] = ['chrome', 'firefox', 'opera', 'requests']

_ROOTS = [
    'C#', 'Db', 'D#', 'Eb', 'F#', 'Gb', 'G#', 'Ab', 'A#', 'Bb',
    'C', 'D', 'E', 'F', 'G', 'A', 'B'
] # akor kök notaları
_SUFFIXES = ['maj7', 'maj', 'm7', 'dim', 'aug', 'sus4', 'sus2', 'm', '7', '9', '5', ''] # akor türleri 
_VALID_CHORDS: set[str] = {r + s for r in _ROOTS for s in _SUFFIXES} # geçerli akor kombinasyonları (örneğin: C, Dm, F#maj7, Ebaug, Gsus4 vb.)
_SINGLE_LETTER_NOISE = {'A', 'B', 'C', 'D', 'E', 'F', 'G'} # tek harfli akorlar genellikle gürültü olabilir, bu yüzden bağlamlarına göre filtrelenecekler.

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    )
}
_TRUSTED_SITES = [
    "repertuarim.com",
    "akormerkezi.com",
    "akor.alternatifim.com",
    "akorlar.com",
]

_OPERA_PATHS = [
    r'C:\Users\Asus\AppData\Local\Programs\Opera\opera.exe',
    r'C:\Program Files\Opera\opera.exe',
    r'C:\Program Files (x86)\Opera\opera.exe',
]

# Selenium tabanlı arama ve akor çekme 

def _get_webdriver(browser: str):

    # Verilen tarayıcı için başsız (headless) Selenium WebDriver döndürür. Selenium yüklü değilse veya tarayıcı bulunamazsa None döner.

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
                return None  # Opera kurulu değil
            opts.add_argument('--headless=new')
            opts.add_argument('--no-sandbox')
            opts.add_argument('--disable-dev-shm-usage')
            return webdriver.Chrome(options=opts)

    except Exception:
        return None


def _search_url_via_browser(query: str, browser: str) -> str | None:

    # Selenium ile DuckDuckGo'da arama yapar, güvenilir bir akor sitesi URL'si döndürür. Bulamazsa None döner.

    driver = _get_webdriver(browser)
    if driver is None:
        return None

    try:
        search_url = (
            'https://duckduckgo.com/?q='
            + urllib.parse.quote(query)
            + '&ia=web'
        )
        driver.get(search_url)
        time.sleep(2.5)  # JS render için bekle.

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            # DuckDuckGo'nun kendi URL'lerini (arama, yönlendirme vb.) atla
            if 'duckduckgo.com' in href:
                continue
            if not href.startswith('http'):
                continue
            if any(site in href for site in _TRUSTED_SITES):
                return href

        return None

    except Exception:
        return None

    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _extract_url_from_ddg(soup: BeautifulSoup) -> str | None:
    for a in soup.find_all('a', class_='result__url'):
        link = a.get('href', '')
        if any(site in link for site in _TRUSTED_SITES):
            if "uddg=" in link:
                return urllib.parse.unquote(link.split("uddg=")[1].split("&")[0])
            return f"https://{link.strip()}" if not link.startswith('http') else link
    return None


def _search_url_via_requests(query: str) -> str | None:

    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        res = requests.get(ddg_url, headers=_HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, 'html.parser')
        return _extract_url_from_ddg(soup)
    except Exception:
        return None


# Aşağıda akor ayıklama ve başarısızlık sözlüğü oluşturma yardımcı fonksiyonları tanımlanmıştır.

def _parse_chords(text: str) -> list[str]:
    pattern = r'\b([A-G][#b]?(?:maj7|maj|m7|dim|aug|sus4|sus2|m|7|9|5)?)\b'
    candidates = re.findall(pattern, text)

    filtered: list[str] = []
    for chord in candidates:
        if chord not in _VALID_CHORDS:
            continue
        if chord in _SINGLE_LETTER_NOISE:
            context_hits = len(re.findall(
                r'(?<!\w)' + re.escape(chord) + r'(?!\w)', text
            ))
            if context_hits > max(5, len(text) // 800):
                continue
        filtered.append(chord)

    seen: set[str] = set()
    unique: list[str] = []
    for c in filtered:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique

# Yardımcı fonksiyon: başarısızlık sözlüğü

def _build_failure(artist: str, song: str, reason: str) -> dict:
    return {
        "success": False,
        "source_url": None,
        "artist": artist,
        "song": song,
        "unique_chords": [],
        "error": reason,
    }

# ANA FONKSİYON

def scrape_chords_from_web(artist: str, song_name: str) -> dict:
    """
    Verilen sanatçı ve şarkı için internet üzerinden akor çeker.

    Arama sırası:
      1. PREFERRED_BROWSER (varsayılan: chrome) ile Selenium arama
      2. Kalan tarayıcılar sırasıyla denenir (firefox → opera)
      3. Hiçbiri çalışmazsa eski requests/DuckDuckGo yöntemiyle devam edilir

    Returns:
        {
            "success": bool,
            "source_url": str | None,
            "artist": str,
            "song": str,
            "unique_chords": list[str],
            "error": str   (yalnızca success=False ise)
        }
    """
    print(f" Web İstihbaratı Toplanıyor: '{artist} - {song_name}'...")

    queries = [
        f"{artist} {song_name} akor repertuarim",
        f"{song_name} akor repertuarim",
        f"{artist} {song_name} akor",
    ]

    # Tarayıcı deneme sırası: önce tercih edilen, sonra diğerleri
    browser_order = [PREFERRED_BROWSER] + [
        b for b in _BROWSER_FALLBACK_ORDER if b != PREFERRED_BROWSER
    ]

    found_url: str | None = None

    for query in queries:
        print(f"    Aranıyor: '{query}'")

        for browser in browser_order:
            if browser == 'requests':
                found_url = _search_url_via_requests(query)
                if found_url:
                    print(f"    Requests yöntemi ile bulundu.")
                    break
            else:
                found_url = _search_url_via_browser(query, browser)
                if found_url:
                    print(f"    {browser.capitalize()} ile bulundu.")
                    break

        if found_url:
            break

        time.sleep(1)

    if not found_url:
        print("    Güvenilir bir akor sitesi bulunamadı.")
        return _build_failure(artist, song_name, "Güvenilir akor sitesi bulunamadı.")

    print(f"    Hedef Site: {found_url}")

    try:
        response = requests.get(found_url, headers=_HEADERS, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        for tag in soup.find_all(['nav', 'header', 'footer', 'script', 'style']):
            tag.decompose()

        text_content = soup.get_text(separator=' ')
        unique_chords = _parse_chords(text_content)

        if not unique_chords:
            return _build_failure(
                artist, song_name,
                f"Site bulundu ({found_url}) ancak geçerli akor ayıklanamadı."
            )

        print(f"    Web'den Çekilen Akorlar: {unique_chords}")
        return {
            "success": True,
            "source_url": found_url,
            "artist": artist,
            "song": song_name,
            "unique_chords": unique_chords,
        }

    except Exception as e:
        print(f"    Site Okuma Hatası: {e}")
        return _build_failure(artist, song_name, f"Site okunamadı: {e}")

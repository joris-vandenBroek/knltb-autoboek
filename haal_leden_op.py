"""
Haal alle leden op van etv-volley.nl en sla op in leden.json

Bekende API-endpoint (gevonden via XHR-interceptie run 22):
  GET /Ajax/Profile/SearchPlayers?term={prefix}
  Response: HTML met Bootstrap <div class="card mb-3"> per speler

Strategie:
1. Login via Selenium (UC + Xvfb, bypass Cloudflare)
2. Navigeer naar de spelerszoek-pagina
3. Extraheer sessie-cookies uit de browser
4. Gebruik requests-library + cookies om de API direct te bevragen
5. Test prefix-lengte 1→2→3 en scan parallel (12 workers)
6. Parseer spelernamen uit HTML-response via regex
7. Sla unieke namen op in leden.json
"""

import os, sys, json, time, logging, re, itertools
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests as req_lib
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

LOGIN_URL     = "https://www.etv-volley.nl/mijn"
RESERVEER_URL = "https://www.etv-volley.nl/mijn/Reservations"
BONDSNUMMER   = os.environ.get("KNLTB_BONDSNUMMER", "")
WACHTWOORD    = os.environ.get("KNLTB_WACHTWOORD", "")
TIMEOUT       = 20

LETTERS = list("abcdefghijklmnopqrstuvwxyz")

# Bekende API-endpoint (HTML-response, Bootstrap cards)
SEARCH_API = "https://www.etv-volley.nl/Ajax/Profile/SearchPlayers?term={q}"

# UI-labels die geen spelernamen zijn
_GEEN_NAAM = {
    "recent mee gespeeld", "recent played", "spelers", "players",
    "zoekresultaten", "search results", "geen resultaten", "no results",
    "recent", "zoeken", "search",
}


# ── Hulpfuncties ──────────────────────────────────────────────────────────────

def screenshot(driver, naam):
    pad = f"{naam}.png"
    try:
        driver.save_screenshot(pad)
        log.info(f"📸 {pad} — URL: {driver.current_url}")
    except Exception as e:
        log.warning(f"Screenshot mislukt ({naam}): {e}")


def chrome_major_versie() -> int | None:
    import subprocess
    for cmd in [["google-chrome", "--version"], ["google-chrome-stable", "--version"],
                ["chromium-browser", "--version"], ["chromium", "--version"]]:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
            m = re.search(r"(\d+)\.", out)
            if m:
                v = int(m.group(1))
                log.info(f"Chrome major versie gedetecteerd: {v}")
                return v
        except Exception:
            pass
    log.warning("Chrome versie niet detecteerbaar")
    return None


def maak_driver():
    opties = uc.ChromeOptions()
    opties.add_argument("--no-sandbox")
    opties.add_argument("--disable-dev-shm-usage")
    opties.add_argument("--disable-gpu")
    opties.add_argument("--window-size=1280,900")
    opties.add_argument("--lang=nl-NL")
    versie = chrome_major_versie()
    driver = uc.Chrome(options=opties, version_main=versie)
    driver.implicitly_wait(3)
    return driver


# ── Login ─────────────────────────────────────────────────────────────────────

def login(driver) -> bool:
    log.info("Navigeer naar loginpagina...")
    driver.get(LOGIN_URL)
    time.sleep(5)
    screenshot(driver, "01_login")
    log.info(f"URL na navigatie: {driver.current_url}")

    page = driver.page_source.lower()
    if ("just a moment" in page or "checking your browser" in page
            or "cf-browser-verification" in page or "sorry, you have been blocked" in page):
        log.error("❌ Cloudflare-blokkade gedetecteerd!")
        screenshot(driver, "01b_cloudflare")
        return False

    # Cookie-banner
    for sel in [
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accepteren')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accepteren')]",
    ]:
        try:
            knop = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, sel)))
            knop.click()
            log.info("🍪 Cookie-banner geaccepteerd")
            time.sleep(1)
            break
        except Exception:
            pass

    if "/mijn" not in driver.current_url:
        log.info(f"Geen /mijn in URL ({driver.current_url}), zoek login-link...")
        for sel in [
            "//a[contains(@href,'/mijn')]",
            "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mijn club')]",
            "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'inloggen')]",
        ]:
            try:
                link = driver.find_element(By.XPATH, sel)
                link.click()
                time.sleep(4)
                screenshot(driver, "01c_na_loginlink")
                break
            except Exception:
                pass

    log.info(f"BONDSNUMMER: {len(BONDSNUMMER)} tekens | WACHTWOORD: {len(WACHTWOORD)} tekens")
    screenshot(driver, "01d_voor_inlogvelden")

    try:
        veld = WebDriverWait(driver, TIMEOUT).until(EC.element_to_be_clickable((By.XPATH,
            "//input[@type='text' or @type='email' or @name='username' or @name='Username' "
            "or @id='username' or @id='Username' "
            "or contains(@placeholder,'bondsnummer') or contains(@placeholder,'gebruikersnaam') "
            "or contains(@placeholder,'e-mail') or contains(@placeholder,'email')]")))
        log.info(f"Gebruikersveld: name='{veld.get_attribute('name')}' id='{veld.get_attribute('id')}'")

        driver.execute_script("""
            var el = arguments[0], val = arguments[1];
            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, veld, BONDSNUMMER)
        log.info(f"Bondsnummer ingevuld via JS")

        ww = WebDriverWait(driver, TIMEOUT).until(EC.element_to_be_clickable((By.XPATH,
            "//input[@type='password']")))
        driver.execute_script("""
            var el = arguments[0], val = arguments[1];
            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, ww, WACHTWOORD)
        log.info(f"Wachtwoord ingevuld via JS")
        time.sleep(1)

        submit_knop = None
        for sel in [
            "//button[@type='submit']",
            "//input[@type='submit']",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'inloggen')]",
        ]:
            try:
                for knop in driver.find_elements(By.XPATH, sel):
                    if knop.is_displayed():
                        log.info(f"Submit: '{knop.text.strip()}'")
                        submit_knop = knop
                        break
                if submit_knop:
                    break
            except Exception:
                pass

        if submit_knop:
            driver.execute_script("arguments[0].click();", submit_knop)
        else:
            ww.send_keys(Keys.RETURN)

        time.sleep(6)
        screenshot(driver, "02_na_login")
        log.info(f"URL na login: {driver.current_url}")

        try:
            body_tekst = driver.find_element(By.TAG_NAME, "body").text
            log.info(f"Paginatekst (eerste 300): {body_tekst[:300]}")
        except Exception:
            pass

        try:
            pw_veld = driver.find_element(By.XPATH, "//input[@type='password']")
            if pw_veld.is_displayed():
                log.error("❌ Inloggen mislukt — wachtwoordveld nog zichtbaar")
                screenshot(driver, "02b_login_mislukt")
                return False
        except Exception:
            pass

        log.info(f"✅ Ingelogd — URL: {driver.current_url}")
        return True

    except TimeoutException as e:
        log.error(f"❌ Login timeout: {e}")
        screenshot(driver, "02_login_fout")
        return False


# ── Navigatie ─────────────────────────────────────────────────────────────────

def naar_spelersselectie(driver) -> bool:
    log.info(f"Navigeer naar {RESERVEER_URL}...")
    driver.get(RESERVEER_URL)
    time.sleep(3)
    screenshot(driver, "03_reserveer_pagina")

    try:
        knop = WebDriverWait(driver, TIMEOUT).until(EC.element_to_be_clickable((By.XPATH,
            "//a[contains(text(),'Baan afhangen') or contains(text(),'afhangen')] "
            "| //button[contains(text(),'Baan afhangen') or contains(text(),'afhangen')]")))
        log.info("'Baan afhangen' knop gevonden, klikken...")
        knop.click()
        time.sleep(4)
        screenshot(driver, "04_spelers_pagina")
        log.info(f"✅ Spelersselectiepagina — URL: {driver.current_url}")
        return True
    except TimeoutException:
        log.error(f"❌ 'Baan afhangen' niet gevonden — URL: {driver.current_url}")
        screenshot(driver, "03b_afhangen_fout")
        return False


def zoek_veld_ophalen(driver):
    try:
        alle = driver.find_elements(By.XPATH, "//input[@type='text' or @type='search']")
        zichtbaar = [v for v in alle if v.is_displayed()]
        log.info(f"Zichtbare text-inputs: {len(zichtbaar)}")
        for v in zichtbaar:
            log.info(f"  placeholder='{v.get_attribute('placeholder')}' id='{v.get_attribute('id')}'")
        if zichtbaar:
            return zichtbaar[0]
    except Exception as e:
        log.error(f"Zoekveld ophalen mislukt: {e}")
    screenshot(driver, "04b_zoekveld_fout")
    return None


# ── API-interceptie ───────────────────────────────────────────────────────────

_INTERCEPTOR_JS = """
window.__apiLog = [];
(function() {
    // Fetch interceptor
    var _origFetch = window.fetch.bind(window);
    window.fetch = function(input, init) {
        var url = (input instanceof Request) ? input.url : String(input || '');
        var p = _origFetch(input, init);
        p.then(function(resp) {
            var clone = resp.clone();
            clone.text().then(function(body) {
                window.__apiLog.push({t:'fetch', url:url, s:resp.status, b:body.slice(0,5000)});
            }).catch(function(){});
        }).catch(function(e) {
            window.__apiLog.push({t:'fetch', url:url, err:String(e)});
        });
        return p;
    };
    // XHR interceptor
    var _origOpen = XMLHttpRequest.prototype.open;
    var _origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(m, url) {
        this.__url = String(url || '');
        return _origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function() {
        var self = this;
        this.addEventListener('loadend', function() {
            window.__apiLog.push({t:'xhr', url:self.__url, s:self.status,
                                   b:(self.responseText||'').slice(0,5000)});
        });
        return _origSend.apply(this, arguments);
    };
})();
console.log('API-interceptor actief');
"""


def injecteer_interceptor(driver):
    driver.execute_script(_INTERCEPTOR_JS)
    log.info("API-interceptor geïnjecteerd")


def extraheer_namen_uit_html(html: str) -> set:
    """
    Parseer spelernamen uit de HTML-response van SearchPlayers.
    De response bevat Bootstrap <div class="card mb-3"> per speler.
    Probeert meerdere patronen om de naam te vinden.
    """
    namen = set()
    if not html:
        return namen

    # Probeer patronen van meest specifiek naar meest breed
    patronen = [
        r'card-title[^>]*>\s*([A-Z][^\n<]{2,58}?)\s*<',       # class="card-title">Naam<
        r'<h[1-6][^>]*>\s*([A-Z][^\n<]{2,58}?)\s*</h[1-6]>',  # <h5>Naam</h5>
        r'<strong[^>]*>\s*([A-Z][^\n<]{2,58}?)\s*</strong>',   # <strong>Naam</strong>
        r'player-name[^>]*>\s*([A-Z][^\n<]{2,58}?)\s*<',       # class="player-name">
        r'full[_-]?name[^>]*>\s*([A-Z][^\n<]{2,58}?)\s*<',     # class="full-name">
        r'data-(?:name|fullname)="([^"]{4,60})"',               # data-name="..."
        r'alt="([A-Z][a-zàáâäèéêëìíîïòóôöùúûü]+(?:\s+(?:van\s+|de\s+|den\s+)?[A-Z][a-zàáâäèéêëìíîïòóôöùúûü]+){1,3})"',  # alt="Voor Achternaam"
    ]

    for patroon in patronen:
        gevonden = re.findall(patroon, html)
        for naam in gevonden:
            naam = naam.strip()
            if naam and len(naam) > 3 and " " in naam and naam.lower() not in _GEEN_NAAM:
                namen.add(naam)
        if namen:
            log.debug(f"HTML-parser: {len(namen)} namen via patroon '{patroon[:40]}'")
            return namen

    # Geen patroon werkte — log de eerste 500 tekens voor diagnose
    log.warning(f"HTML-parser: geen namen gevonden. HTML snippet: {html[:500]}")
    return namen


def extraheer_namen_uit_data(data) -> set:
    """Flexibel JSON-schema → set van spelernamen (fallback als API JSON retourneert)."""
    namen = set()
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = None
        for key in ["results", "players", "members", "data", "items", "users",
                    "suggestions", "value", "Values"]:
            if isinstance(data.get(key), list):
                items = data[key]
                break
        if items is None:
            items = []
    else:
        return namen

    for item in items:
        if isinstance(item, str):
            naam = item.strip()
        elif isinstance(item, dict):
            naam = (item.get("name") or item.get("fullName") or item.get("full_name") or
                    item.get("displayName") or item.get("display_name") or
                    item.get("label") or item.get("text") or item.get("value") or "")
            if not naam:
                v = (item.get("firstName") or item.get("first_name") or "")
                a = (item.get("lastName") or item.get("last_name") or item.get("surname") or "")
                naam = f"{v} {a}".strip()
        else:
            naam = ""

        naam = naam.strip()
        if naam and len(naam) > 3 and " " in naam and naam.lower() not in _GEEN_NAAM:
            namen.add(naam)
    return namen


def vind_speler_api(driver, zoek_veld) -> dict | None:
    """
    Typ 3 letters, vang XHR/fetch op, retourneer info over gevonden API.
    """
    driver.execute_script("window.__apiLog = [];")

    zoek_veld.clear()
    zoek_veld.send_keys("van")
    time.sleep(4)

    api_log = driver.execute_script("return window.__apiLog || [];")
    log.info(f"=== API-log na 'van' ({len(api_log)} entries) ===")

    kandidaten = []
    for entry in api_log:
        url    = entry.get("url", "")
        body   = entry.get("b", "")
        status = entry.get("s", 0)
        log.info(f"  [{entry.get('t')}] {url} (HTTP {status}) body_len={len(body)}")
        if body and len(body) > 5:
            log.info(f"    body[:300]: {body[:300]}")
        # Kandidaat: JSON-response met status 200
        if status == 200 and body.strip().startswith(("[", "{")):
            kandidaten.append(entry)

    zoek_veld.clear()

    # Zoek de entry die echte namen bevat
    for entry in kandidaten:
        body = entry.get("b", "")
        try:
            data  = json.loads(body)
            namen = extraheer_namen_uit_data(data)
            if namen:
                log.info(f"✅ Speler-API bevestigd: {entry['url']}")
                log.info(f"   Voorbeeldnamen: {sorted(namen)[:5]}")
                return {
                    "url":   entry["url"],
                    "data":  data,
                    "namen": namen,
                }
        except Exception:
            pass

    # Tweede kans: alle JSON-kandidaten loggen
    if kandidaten:
        log.warning("Geen speler-API met namen gevonden. Alle JSON-kandidaten:")
        for e in kandidaten:
            log.warning(f"  {e.get('url','')} — body: {e.get('b','')[:200]}")
    else:
        log.warning("Geen JSON-responses in api-log — interceptor werkt mogelijk niet")

    return None


def bouw_url_template(api_url: str, zoekterm: str = "van") -> str:
    """Vervang de zoekterm in de URL door {q}."""
    if zoekterm in api_url:
        return api_url.replace(zoekterm, "{q}", 1)
    # Probeer query-parameters
    template = re.sub(
        r"([?&][^=]+=)[^&]*",
        lambda m: m.group(0) if "{q}" in m.group(0) else m.group(1) + "{q}",
        api_url,
        count=1,
    )
    return template


# ── Directe API-scan ──────────────────────────────────────────────────────────

def haal_alle_leden_via_browser(driver, template: str) -> set:
    """
    Gebruik de browser zelf voor alle API-aanroepen.
    De browser heeft geldige Cloudflare-cookies (requests-library werkt niet).

    Strategie:
    - Genereer alle 3-letter prefixen (17 576)
    - Verstuur in batches van 50 parallelle fetch()-aanroepen via JS
    - Parseer HTML-response met browser's eigen DOMParser
    - Extraheer spelernamen uit .addPlayer cards
    """
    alle_namen = set()
    prefixen3  = [a + b + c for a, b, c in itertools.product(LETTERS, repeat=3)]

    # Test eerst kortere prefixen
    def browser_zoek(prefix: str) -> list:
        url = template.replace("{q}", prefix)
        driver.set_script_timeout(30)
        try:
            return driver.execute_async_script("""
                var url      = arguments[0];
                var callback = arguments[arguments.length - 1];
                fetch(url, {
                    credentials: 'include',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'text/html, */*'
                    }
                }).then(function(r) { return r.text(); })
                  .then(function(html) {
                      var parser = new DOMParser();
                      var doc    = parser.parseFromString(html, 'text/html');
                      var namen  = [];
                      // Kaarten met spelergegevens
                      doc.querySelectorAll('.addPlayer').forEach(function(card) {
                          var naam = card.getAttribute('data-name')
                                  || card.getAttribute('data-fullname')
                                  || card.getAttribute('data-player-name');
                          if (!naam) {
                              var el = card.querySelector(
                                  'h1,h2,h3,h4,h5,h6,.card-title,strong');
                              if (el) naam = el.textContent.trim();
                          }
                          if (!naam) {
                              // Clone, verwijder afbeeldingen/badges, pak tekst
                              var clone = card.cloneNode(true);
                              clone.querySelectorAll('img,button,.badge,small')
                                   .forEach(function(e) { e.remove(); });
                              naam = clone.textContent.replace(/\\s+/g,' ').trim()
                                         .split('\\n')[0].trim();
                          }
                          if (naam && naam.length > 3 && naam.indexOf(' ') >= 0)
                              namen.push(naam);
                      });
                      // Fallback: card-title buiten .addPlayer
                      if (!namen.length) {
                          doc.querySelectorAll('.card-title').forEach(function(el) {
                              var t = el.textContent.trim();
                              if (t && t.length > 3 && t.indexOf(' ') >= 0) namen.push(t);
                          });
                      }
                      callback(namen);
                  }).catch(function() { callback([]); });
            """, url) or []
        except Exception as e:
            log.debug(f"browser_zoek '{prefix}' fout: {e}")
            return []

    # ── Diagnose: log kaart-HTML zodat we de structuur kunnen zien ──────────
    driver.set_script_timeout(30)
    try:
        diag = driver.execute_async_script("""
            var url = arguments[0], cb = arguments[arguments.length - 1];
            fetch(url, {credentials:'include',
                headers:{'X-Requested-With':'XMLHttpRequest','Accept':'text/html,*/*'}})
            .then(function(r){return r.text();})
            .then(function(html){
                var doc   = new DOMParser().parseFromString(html,'text/html');
                var cards = doc.querySelectorAll('.addPlayer');
                cb({raw: html.slice(0,1500),
                    cards: cards.length,
                    first: cards.length ? cards[0].outerHTML.slice(0,800) : ''});
            }).catch(function(e){cb({err:String(e)});});
        """, template.replace("{q}", "van"))
        log.info(f"Diagnose 'van': cards={diag.get('cards', 0)}")
        log.info(f"  Eerste kaart HTML: {diag.get('first', '(geen)')}")
        log.info(f"  Raw HTML start: {diag.get('raw', '')[:400]}")
    except Exception as e:
        log.warning(f"Diagnose mislukt: {e}")

    # Lege query
    leeg = browser_zoek("")
    if len(leeg) > 5:
        log.info(f"Lege query geeft {len(leeg)} namen — klaar!")
        return set(leeg)

    # 1 letter
    test1 = browser_zoek("j")
    if test1:
        log.info(f"1-letter werkt ('j'→{len(test1)}). Scan 26 letters...")
        namen = set()
        for l in LETTERS:
            namen.update(browser_zoek(l))
        return namen

    # 2 letters
    test2 = browser_zoek("jo")
    if test2:
        log.info(f"2-letter werkt ('jo'→{len(test2)}). Scan 676 combinaties...")
        namen  = set()
        prefixen2 = [a + b for a, b in itertools.product(LETTERS, repeat=2)]
        for i, p in enumerate(prefixen2):
            namen.update(browser_zoek(p))
            if (i + 1) % 100 == 0:
                log.info(f"  {i+1}/676 — {len(namen)} namen")
        return namen

    # 3-letter scan in batches van 50 parallelle fetches
    BATCH = 50
    total = len(prefixen3)
    total_batches = (total + BATCH - 1) // BATCH
    log.info(f"3-letter scan: {total} prefixen, batches van {BATCH} ({total_batches} batches)")

    driver.set_script_timeout(60)  # 60s per batch

    for batch_nr, start in enumerate(range(0, total, BATCH)):
        batch_urls = [template.replace("{q}", p) for p in prefixen3[start:start + BATCH]]
        try:
            namen_batch = driver.execute_async_script("""
                var urls     = arguments[0];
                var callback = arguments[arguments.length - 1];
                Promise.all(urls.map(function(url) {
                    return fetch(url, {
                        credentials: 'include',
                        headers: {
                            'X-Requested-With': 'XMLHttpRequest',
                            'Accept': 'text/html, */*'
                        }
                    }).then(function(r) { return r.text(); })
                      .catch(function() { return ''; });
                })).then(function(htmlList) {
                    var namen  = [];
                    var parser = new DOMParser();
                    htmlList.forEach(function(html) {
                        if (!html) return;
                        var doc = parser.parseFromString(html, 'text/html');
                        doc.querySelectorAll('.addPlayer').forEach(function(card) {
                            var naam = card.getAttribute('data-name')
                                    || card.getAttribute('data-fullname')
                                    || card.getAttribute('data-player-name');
                            if (!naam) {
                                var el = card.querySelector(
                                    'h1,h2,h3,h4,h5,h6,.card-title,strong');
                                if (el) naam = el.textContent.trim();
                            }
                            if (!naam) {
                                var clone = card.cloneNode(true);
                                clone.querySelectorAll('img,button,.badge,small')
                                     .forEach(function(e) { e.remove(); });
                                naam = clone.textContent.replace(/\\s+/g,' ').trim()
                                            .split('\\n')[0].trim();
                            }
                            if (naam && naam.length > 3 && naam.indexOf(' ') >= 0)
                                namen.push(naam);
                        });
                        // Fallback card-title
                        if (!namen.length) {
                            doc.querySelectorAll('.card-title').forEach(function(el) {
                                var t = el.textContent.trim();
                                if (t && t.length > 3 && t.indexOf(' ') >= 0) namen.push(t);
                            });
                        }
                    });
                    callback(namen);
                }).catch(function(e) { callback([]); });
            """, batch_urls) or []

            for naam in namen_batch:
                naam = naam.strip()
                if naam and len(naam) > 3 and " " in naam and naam.lower() not in _GEEN_NAAM:
                    alle_namen.add(naam)

        except Exception as e:
            log.warning(f"Batch {batch_nr + 1}/{total_batches} fout: {e}")

        if (batch_nr + 1) % 20 == 0:
            log.info(f"  Batch {batch_nr + 1}/{total_batches} — {len(alle_namen)} namen tot nu toe")

    return alle_namen


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not BONDSNUMMER or not WACHTWOORD:
        log.error("❌ Stel KNLTB_BONDSNUMMER en KNLTB_WACHTWOORD in als GitHub Secrets")
        sys.exit(1)

    driver = maak_driver()
    alle_namen = set()

    try:
        if not login(driver):
            log.error("Login mislukt")
            sys.exit(1)

        if not naar_spelersselectie(driver):
            log.error("Navigatie mislukt")
            sys.exit(1)

        zoek_veld = zoek_veld_ophalen(driver)
        if not zoek_veld:
            log.error("Zoekveld niet gevonden")
            sys.exit(1)

        # Interceptor: bevestig/verfijn API-endpoint
        injecteer_interceptor(driver)
        api_info = vind_speler_api(driver, zoek_veld)

        if api_info:
            alle_namen.update(api_info["namen"])
            log.info(f"Interceptor bevestigde API: {api_info['url']}")
            template = bouw_url_template(api_info["url"], "van")
        else:
            log.info(f"Gebruik bekende API-endpoint: {SEARCH_API}")
            template = SEARCH_API

        log.info(f"API template: {template}")
        screenshot(driver, "05_voor_api_scan")

        # --- Browser-gebaseerde scan (requests werkt niet: Cloudflare-fingerprinting) ---
        browser_namen = haal_alle_leden_via_browser(driver, template)
        alle_namen.update(browser_namen)
        log.info(f"Na browser-scan: {len(alle_namen)} unieke namen")

    finally:
        if driver:
            try:
                screenshot(driver, "99_einde")
            except Exception:
                pass
            driver.quit()

    alle_namen = {n for n in alle_namen if n.lower() not in _GEEN_NAAM}

    if not alle_namen:
        log.warning("⚠️ Geen leden gevonden — leden.json wordt NIET overschreven")
        sys.exit(1)

    gesorteerd = sorted(alle_namen)
    with open("leden.json", "w", encoding="utf-8") as f:
        json.dump(gesorteerd, f, ensure_ascii=False, indent=2)

    log.info(f"✅ {len(gesorteerd)} leden opgeslagen in leden.json")
    log.info(f"   Eerste 10: {gesorteerd[:10]}")


if __name__ == "__main__":
    main()

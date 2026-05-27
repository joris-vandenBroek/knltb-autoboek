"""
Haal alle leden op van etv-volley.nl en sla op in leden.json

Strategie:
1. Login via Selenium (UC + Xvfb, geen headless, bypass Cloudflare)
2. Navigeer naar de spelerszoek-pagina
3. Injecteer XHR/fetch-interceptor in de pagina
4. Typ 'van' (3 letters) → vang de API-aanroep + JSON-response op
5. Extraheer de API-URL-template
6. Gebruik requests-library met sessie-cookies om alle 3-letter-prefixen
   systematisch te bevragen (parallel, snel)
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


def extraheer_namen_uit_data(data) -> set:
    """Flexibel JSON-schema → set van spelernamen."""
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

def haal_alle_leden_via_api(template: str, cookies: dict, user_agent: str) -> set:
    """
    Systematisch alle leden ophalen via directe HTTP-aanroepen.
    Test prefix-lengte 1→2→3 en gebruikt parallelle requests.
    """
    if not REQUESTS_OK:
        log.error("requests library niet beschikbaar — kan API niet direct bevragen")
        return set()

    headers = {
        "Accept":           "application/json, */*",
        "User-Agent":       user_agent,
        "X-Requested-With": "XMLHttpRequest",
    }

    def maak_sessie():
        s = req_lib.Session()
        s.cookies.update(cookies)
        s.headers.update(headers)
        return s

    def zoek(prefix: str) -> set:
        url = template.replace("{q}", prefix)
        try:
            resp = maak_sessie().get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                namen = extraheer_namen_uit_data(data)
                if namen:
                    log.debug(f"  '{prefix}' → {len(namen)} namen")
                return namen
        except Exception as e:
            log.debug(f"  '{prefix}' fout: {e}")
        return set()

    def parallel_zoek(prefixen: list, workers: int = 8) -> set:
        namen = set()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(zoek, p): p for p in prefixen}
            for i, fut in enumerate(as_completed(futures)):
                namen.update(fut.result())
                if (i + 1) % 200 == 0:
                    log.info(f"  {i+1}/{len(prefixen)} klaar — {len(namen)} namen tot nu toe")
        return namen

    log.info(f"API template: {template}")

    # Test lengte 0 (alles in één keer?)
    leeg = zoek("")
    if len(leeg) > 5:
        log.info(f"Lege query retourneert {len(leeg)} namen — klaar!")
        return leeg

    # Test lengte 1
    test1 = zoek("j")
    if test1:
        log.info(f"1-letter queries werken ('j'→{len(test1)}). Scan 26 letters...")
        return parallel_zoek(LETTERS, workers=8)

    # Test lengte 2
    test2 = zoek("jo")
    if test2:
        log.info(f"2-letter queries werken ('jo'→{len(test2)}). Scan 676 combinaties...")
        prefixen = [a + b for a, b in itertools.product(LETTERS, repeat=2)]
        return parallel_zoek(prefixen, workers=8)

    # 3-letter scan (frontend-minimum)
    log.info("3-letter queries nodig. Scan 17 576 combinaties (parallel, ~3 min)...")
    prefixen = [a + b + c for a, b, c in itertools.product(LETTERS, repeat=3)]
    return parallel_zoek(prefixen, workers=12)


# ── Fallback: Selenium autocomplete ──────────────────────────────────────────

def haal_leden_via_selenium(driver, zoek_veld) -> set:
    """
    Fallback als API niet gevonden wordt: typ 3-letter-combinaties en
    verzamel autocomplete-suggesties via Selenium.
    Gebruikt veelvoorkomende Nederlandse 3-letter naam-starts.
    """
    namen = set()

    # Genereer 3-letter combinaties voor veelvoorkomende Nederlandse namen
    # Dekt voor/achternamen die starten met frequente patronen
    prefixen_3 = []
    # Alle combinaties van eerste 2 letters: 676 -> voeg derde letter toe
    # Maar beperk: alleen letters die zinvol zijn voor Ned. namen
    for a, b, c in itertools.product(LETTERS, repeat=3):
        prefixen_3.append(a + b + c)

    log.info(f"Selenium fallback: {len(prefixen_3)} 3-letter prefixen")

    for i, term in enumerate(prefixen_3):
        try:
            zoek_veld.clear()
            zoek_veld.send_keys(term)
            time.sleep(1.5)

            # Verzamel suggesties via ARIA + CSS
            for sel in [
                "//*[@role='option']",
                "//li[contains(@class,'player') or contains(@class,'suggestion') or contains(@class,'result') or contains(@class,'item')]",
                "//div[contains(@class,'player') or contains(@class,'suggestion') or contains(@class,'result')]//span[string-length(normalize-space(text()))>3]",
            ]:
                try:
                    for el in driver.find_elements(By.XPATH, sel):
                        if el.is_displayed():
                            tekst = el.text.strip()
                            if tekst and len(tekst) > 3 and " " in tekst and tekst.lower() not in _GEEN_NAAM:
                                namen.add(tekst)
                except Exception:
                    pass

            zoek_veld.clear()
            time.sleep(0.3)

            if (i + 1) % 500 == 0:
                log.info(f"  {i+1}/{len(prefixen_3)} — {len(namen)} namen tot nu toe")
                screenshot(driver, f"05_zoeken_{i+1}")

        except Exception as e:
            log.warning(f"Fout bij '{term}': {e}")
            zoek_veld = zoek_veld_ophalen(driver)
            if not zoek_veld:
                break

    return namen


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

        zoek = zoek_veld_ophalen(driver)
        if not zoek:
            log.error("Zoekveld niet gevonden")
            sys.exit(1)

        # --- Stap 1: injecteer interceptor en vind de API ---
        injecteer_interceptor(driver)
        api_info = vind_speler_api(driver, zoek)

        if api_info:
            # Namen uit de eerste 'van'-query direct toevoegen
            alle_namen.update(api_info["namen"])
            log.info(f"Eerste API-query al {len(alle_namen)} namen")

            template = bouw_url_template(api_info["url"], "van")
            log.info(f"API-template: {template}")

            # Extraheer cookies en user-agent
            cookies    = {c["name"]: c["value"] for c in driver.get_cookies()}
            user_agent = driver.execute_script("return navigator.userAgent;")

            # Sluit browser zo vroeg mogelijk (sessie-cookies blijven geldig)
            screenshot(driver, "05_voor_api_scan")
            driver.quit()
            driver = None

            # --- Stap 2: haal alle leden op via directe API ---
            api_namen = haal_alle_leden_via_api(template, cookies, user_agent)
            alle_namen.update(api_namen)
            log.info(f"Na API-scan: {len(alle_namen)} unieke namen")

        else:
            # --- Fallback: Selenium autocomplete met 3-letter prefixen ---
            log.warning("API niet gevonden — gebruik Selenium autocomplete fallback")
            zoek = zoek_veld_ophalen(driver)
            if zoek:
                alle_namen.update(haal_leden_via_selenium(driver, zoek))

    finally:
        if driver:
            screenshot(driver, "99_einde")
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

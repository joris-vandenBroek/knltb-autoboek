"""
Haal padel speelsterktes op van mijnknltb.toernooi.nl en voeg toe aan leden.json.

Strategie:
1. Lees leden.json (bevat naam + bondsnummer per lid)
2. Login op mijnknltb.toernooi.nl via Selenium (verwerkt login-formulier + cookies)
3. Kopieer cookies naar requests-sessie voor snelle HTTP-calls
4. Per lid:
   a. GET /find/player/DoSearch?Query={bondsnummer} → zoek player-profile link
   b. GET /player-profile/{guid} → extraheer 'Padel Dubbel' speelsterkte uit HTML
   Geen Selenium-navigatie per lid → geen sessie-expiry door pagina-limiet
5. Schrijf sterktes terug naar leden.json
"""

import os, sys, json, time, re, logging
import requests
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

MIJNKNLTB_URL = "https://mijnknltb.toernooi.nl"
BONDSNUMMER   = os.environ.get("KNLTB_BONDSNUMMER", "")
WACHTWOORD    = os.environ.get("KNLTB_WACHTWOORD", "")
MAX_LEDEN     = int(os.environ.get("MAX_LEDEN", "0") or "0")

# Elke N leden cookies verversen via Selenium om sessieverval te voorkomen
COOKIE_REFRESH_INTERVAL = 50


def screenshot(driver, naam):
    try:
        driver.save_screenshot(f"{naam}.png")
        log.info(f"Screenshot: {naam}.png — URL: {driver.current_url}")
    except Exception as e:
        log.warning(f"Screenshot mislukt ({naam}): {e}")


def chrome_major_versie():
    import subprocess
    for cmd in [["google-chrome", "--version"], ["google-chrome-stable", "--version"],
                ["chromium-browser", "--version"], ["chromium", "--version"]]:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
            m = re.search(r"(\d+)\.", out)
            if m:
                v = int(m.group(1))
                log.info(f"Chrome versie: {v}")
                return v
        except Exception:
            pass
    return None


def maak_driver():
    opties = uc.ChromeOptions()
    opties.add_argument("--no-sandbox")
    opties.add_argument("--disable-dev-shm-usage")
    opties.add_argument("--disable-gpu")
    opties.add_argument("--window-size=1280,900")
    opties.add_argument("--lang=nl-NL")
    driver = uc.Chrome(options=opties, version_main=chrome_major_versie())
    driver.implicitly_wait(3)
    return driver


def login_mijnknltb(driver) -> bool:
    """Login op mijnknltb.toernooi.nl via Selenium. Geeft True als geslaagd."""
    log.info("Login op mijnknltb.toernooi.nl...")
    driver.get(f"{MIJNKNLTB_URL}/user/login")
    time.sleep(2)

    # Accepteer cookie-wall
    try:
        WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='Akkoord']"))
        ).click()
        log.info("Cookie-wall geaccepteerd")
        time.sleep(1)
    except Exception:
        pass

    try:
        veld_nr = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[@name='Username' or @id='Username' or @type='text']"))
        )
        veld_nr.clear()
        veld_nr.send_keys(BONDSNUMMER)
        veld_pw = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        veld_pw.clear()
        veld_pw.send_keys(WACHTWOORD)
        veld_pw.send_keys(Keys.RETURN)
        time.sleep(4)

        if "login" not in driver.current_url.lower():
            log.info(f"Login geslaagd: {driver.current_url}")
            return True
        else:
            log.error(f"Login mislukt: {driver.current_url}")
            screenshot(driver, "knltb_login_fout")
            return False
    except Exception as e:
        log.error(f"Login fout: {e}")
        screenshot(driver, "knltb_login_fout")
        return False


def haal_cookies(driver) -> dict:
    """Kopieer Selenium-cookies naar dict voor requests."""
    return {c['name']: c['value'] for c in driver.get_cookies()}


def maak_requests_sessie(driver) -> requests.Session:
    """Maak requests.Session met cookies en headers uit Selenium-sessie."""
    session = requests.Session()
    session.cookies.update(haal_cookies(driver))
    ua = driver.execute_script("return navigator.userAgent") or \
         "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    session.headers.update({
        "User-Agent": ua,
        "Accept-Language": "nl-NL,nl;q=0.9",
        "Referer": f"{MIJNKNLTB_URL}/find/player",
    })
    log.info("requests-sessie aangemaakt")
    return session


def ververs_cookies(driver, session) -> bool:
    """
    Ververs cookies in requests-sessie vanuit Selenium.
    Navigeer kort naar home om sessie levend te houden.
    """
    log.info("Cookies verversen...")
    driver.get(f"{MIJNKNLTB_URL}/")
    time.sleep(2)
    if "login" in driver.current_url.lower():
        log.warning("Sessie verlopen tijdens cookie-refresh — opnieuw inloggen")
        if not login_mijnknltb(driver):
            return False
    session.cookies.update(haal_cookies(driver))
    log.info("Cookies bijgewerkt")
    return True


def zoek_profiel_url(session, bondsnummer: str) -> str | None:
    """
    Zoek spelersprofiel via AJAX DoSearch-endpoint.
    Geeft player-profile URL of None.
    """
    try:
        resp = session.get(
            f"{MIJNKNLTB_URL}/find/player/DoSearch",
            params={"Query": bondsnummer, "Page": "1", "SportID": "0"},
            headers={"X-Requested-With": "XMLHttpRequest"},
            timeout=15,
        )
        if "login" in resp.url:
            log.warning(f"  DoSearch redirect naar login voor {bondsnummer}")
            return None
        # Zoek player-profile links in HTML-fragment
        matches = re.findall(r'href="(/player-profile/[^"]+)"', resp.text)
        if matches:
            log.info(f"  DoSearch: {len(matches)} profiellink(s) gevonden voor {bondsnummer}")
            return MIJNKNLTB_URL + matches[0]
        log.warning(f"  DoSearch: geen profiellink gevonden voor {bondsnummer} (status={resp.status_code}, len={len(resp.text)})")
        # Log stukje response voor diagnose
        log.debug(f"  DoSearch response snippet: {resp.text[:200]!r}")
        return None
    except Exception as e:
        log.warning(f"  DoSearch fout voor {bondsnummer}: {e}")
        return None


def haal_padel_sterkte_van_profiel(session, profiel_url: str, bondsnummer: str) -> dict:
    """
    Haal padel sterkte op van player-profile pagina via HTTP request.
    Geeft {'sterkte': '7', 'rating': '7,32'} of {} bij mislukking.
    """
    try:
        resp = session.get(profiel_url, timeout=15)
        if "login" in resp.url:
            log.warning(f"  Profiel redirect naar login: {resp.url}")
            return None  # None = sessie verlopen
        # Zoek Padel Dubbel span in server-rendered HTML
        m = re.search(
            r'title="Padel Dubbel"[^>]*>.*?'
            r'<span class="tag-duo__title">(.*?)</span>.*?'
            r'<span class="tag-duo__value">(.*?)</span>',
            resp.text, re.DOTALL
        )
        if m:
            sterkte_raw = m.group(1)
            rating = m.group(2).strip()
            # Verwijder SVG-tags en witruimte uit sterkte
            sterkte = re.sub(r'<[^>]+>', '', sterkte_raw).strip()
            log.info(f"  ✅ {bondsnummer}: sterkte={sterkte}, rating={rating}")
            return {'sterkte': sterkte, 'rating': rating}
        log.warning(f"  ⚠️  {bondsnummer}: geen 'Padel Dubbel' span op {profiel_url}")
        return {}
    except Exception as e:
        log.warning(f"  Profiel request fout voor {bondsnummer}: {e}")
        return {}


def haal_padel_sterkte(driver, session, bondsnummer: str, idx: int = 0) -> dict:
    """
    Volledig ophaalproces voor één lid:
    1. DoSearch → player-profile URL
    2. Profiel request → padel sterkte
    Geeft {'sterkte': ..., 'rating': ...} of {} bij mislukking.
    """
    # Stap 1: zoek profiel-URL via AJAX
    profiel_url = zoek_profiel_url(session, bondsnummer)
    if not profiel_url:
        # Probeer cookies te verversen en opnieuw
        log.info(f"  Geen profiellink — cookies verversen en herproberen")
        if ververs_cookies(driver, session):
            profiel_url = zoek_profiel_url(session, bondsnummer)
        if not profiel_url:
            log.warning(f"  ❌ Geen profiel gevonden voor {bondsnummer}")
            return {}

    # Stap 2: haal padel sterkte op van profielpagina
    result = haal_padel_sterkte_van_profiel(session, profiel_url, bondsnummer)
    if result is None:
        # Sessie verlopen — cookies verversen
        log.warning(f"  Sessie verlopen bij profiel — cookies verversen")
        if ververs_cookies(driver, session):
            result = haal_padel_sterkte_van_profiel(session, profiel_url, bondsnummer)
        if not result:
            return {}

    return result


def main():
    if not BONDSNUMMER or not WACHTWOORD:
        log.error("Stel KNLTB_BONDSNUMMER en KNLTB_WACHTWOORD in als GitHub Secrets")
        sys.exit(1)

    # Lees huidige leden.json
    try:
        with open("leden.json", encoding="utf-8") as f:
            leden_lijst = json.load(f)
    except Exception as e:
        log.error(f"Kan leden.json niet lezen: {e}")
        sys.exit(1)

    leden_lijst = [
        item if isinstance(item, dict) else {'naam': item, 'bondsnummer': ''}
        for item in leden_lijst
    ]

    te_verwerken = leden_lijst[:MAX_LEDEN] if MAX_LEDEN > 0 else leden_lijst
    if MAX_LEDEN > 0:
        log.info(f"MAX_LEDEN={MAX_LEDEN} — verwerk eerste {MAX_LEDEN} van {len(leden_lijst)} leden")

    met_bondsnummer = [l for l in te_verwerken if l.get('bondsnummer', '').strip()]
    log.info(f"{len(te_verwerken)} leden te verwerken, {len(met_bondsnummer)} met bondsnummer")

    # Login via Selenium, daarna requests gebruiken voor alle lookups
    driver = maak_driver()
    session = None

    try:
        if not login_mijnknltb(driver):
            log.error("Login mislukt — script stopt")
            sys.exit(1)

        # Navigeer naar search-pagina om search-gerelateerde cookies te zetten
        driver.get(f"{MIJNKNLTB_URL}/find/player")
        time.sleep(2)
        screenshot(driver, "00_find_player")

        session = maak_requests_sessie(driver)

        for i, lid in enumerate(te_verwerken):
            bnr = lid.get('bondsnummer', '').strip()
            if not bnr:
                log.info(f"  [{i+1}/{len(leden_lijst)}] {lid['naam']}: geen bondsnummer")
                lid.setdefault('sterkte_padel', '')
                lid.setdefault('rating_padel', '')
                continue

            log.info(f"[{i+1}/{len(leden_lijst)}] {lid['naam']} ({bnr})")

            # Cookies periodiek verversen
            if i > 0 and i % COOKIE_REFRESH_INTERVAL == 0:
                log.info(f"Periodieke cookie-refresh na {i} leden")
                ververs_cookies(driver, session)

            data = haal_padel_sterkte(driver, session, bnr, idx=i)
            lid['sterkte_padel'] = data.get('sterkte', '')
            lid['rating_padel']  = data.get('rating', '')

    finally:
        try:
            screenshot(driver, "99_einde")
        except Exception:
            pass
        driver.quit()

    # Schrijf altijd de volledige lijst terug (ook als MAX_LEDEN beperkt was)
    with open("leden.json", "w", encoding="utf-8") as f:
        json.dump(leden_lijst, f, ensure_ascii=False, indent=2)

    met_sterkte = sum(1 for l in leden_lijst if l.get('sterkte_padel'))
    log.info(f"Klaar: sterkte aanwezig voor {met_sterkte}/{len(leden_lijst)} leden")
    log.info(f"Opgeslagen in leden.json")


if __name__ == "__main__":
    main()

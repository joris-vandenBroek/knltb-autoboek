"""
Haal alle leden op van de Ledenlijst-pagina op etv-volley.nl
en sla op in leden.json, inclusief padel speelsterkte van mijnknltb.toernooi.nl.

Strategie:
1. Login via Selenium (UC + Xvfb, bypass Cloudflare) op etv-volley.nl
2. Navigeer naar de Ledenlijst-tab
3. Scrape alle namen + bondsnummers uit de HTML-tabel (kolom 0 + 1)
4. Herhaal scrollen/paginering totdat er geen nieuwe namen meer bijkomen
5. Login op mijnknltb.toernooi.nl met dezelfde credentials
6. Per lid: zoek profiel via bondsnummer, haal padel dubbel speelsterkte op
7. Sla op in leden.json als lijst van objecten met naam, bondsnummer en sterkte_padel
"""

import os, sys, json, time, logging
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

LOGIN_URL        = "https://www.etv-volley.nl/mijn"
MIJNKNLTB_URL    = "https://mijnknltb.toernooi.nl"
BONDSNUMMER      = os.environ.get("KNLTB_BONDSNUMMER", "")
WACHTWOORD       = os.environ.get("KNLTB_WACHTWOORD", "")
TIMEOUT          = 20


def screenshot(driver, naam):
    try:
        driver.save_screenshot(f"{naam}.png")
        log.info(f"Screenshot: {naam}.png — URL: {driver.current_url}")
    except Exception as e:
        log.warning(f"Screenshot mislukt ({naam}): {e}")


def chrome_major_versie():
    import subprocess, re
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


def login(driver) -> bool:
    """Login op etv-volley.nl via etv_common."""
    from etv_common import login as _common_login
    return _common_login(
        driver,
        bondsnummer=BONDSNUMMER,
        wachtwoord=WACHTWOORD,
        login_url=LOGIN_URL,
        screenshot=screenshot,
    )


def naar_ledenlijst(driver) -> bool:
    """Klik op de Ledenlijst-tab in de navigatie."""
    log.info("Navigeer naar Ledenlijst...")

    for sel in [
        "//a[contains(.,'Ledenlijst')]",
        "//a[contains(@href,'Member') or contains(@href,'Leden')]",
        "//*[@role='tab'][contains(.,'Ledenlijst')]",
    ]:
        try:
            link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, sel)))
            href = link.get_attribute("href") or ""
            log.info(f"Ledenlijst-link gevonden: '{link.text.strip()}' href='{href}'")
            driver.execute_script("arguments[0].click();", link)
            time.sleep(3)
            screenshot(driver, "03_ledenlijst")
            log.info(f"URL na klik: {driver.current_url}")
            return True
        except TimeoutException:
            pass

    log.error("Ledenlijst-link niet gevonden")
    screenshot(driver, "03_ledenlijst_fout")
    return False


def haal_leden_van_pagina(driver) -> list:
    """Extraheer naam (kolom 0) + bondsnummer (kolom 1) uit de zichtbare tabel."""
    return driver.execute_script("""
        var leden = [];
        var rijen = document.querySelectorAll('table tr');
        rijen.forEach(function(rij) {
            var cellen = rij.querySelectorAll('td');
            if (!cellen.length) return;  // headerrij
            var naam = cellen[0].textContent.trim();
            var bondsnummer = cellen[1] ? cellen[1].textContent.trim() : '';
            if (naam && naam.length > 3 && naam.indexOf(' ') >= 0)
                leden.push({naam: naam, bondsnummer: bondsnummer});
        });
        return leden;
    """) or []


def scrape_ledenlijst(driver) -> list:
    """
    Scrape alle leden (naam + bondsnummer) uit de ledenlijst.
    Handelt paginering af; deduplicatie op bondsnummer.
    """
    alle_leden = {}  # bondsnummer -> {naam, bondsnummer}

    # Wacht tot de tabel geladen is
    try:
        WebDriverWait(driver, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, "table tr td")) > 0
        )
        log.info("Tabel zichtbaar")
    except TimeoutException:
        log.warning("Tabel niet gevonden na 15s — toch proberen")

    screenshot(driver, "04_tabel_geladen")

    def verwerk_batch(leden):
        nieuw = 0
        for lid in leden:
            key = lid.get('bondsnummer') or lid['naam']
            if key not in alle_leden:
                alle_leden[key] = lid
                nieuw += 1
        return nieuw

    # Eerste batch
    leden = haal_leden_van_pagina(driver)
    nieuw = verwerk_batch(leden)
    log.info(f"Eerste batch: {len(leden)} rijen, {nieuw} nieuw")

    # Paginering
    pagina = 1
    while True:
        volgende = None

        try:
            kandidaten = driver.find_elements(By.XPATH,
                f"//a[normalize-space(.)='{pagina + 1}']")
            for el in kandidaten:
                if el.is_displayed() and el.is_enabled():
                    volgende = el
                    break
        except Exception:
            pass

        if not volgende:
            for sel in [
                "//a[normalize-space(.)='»' or normalize-space(.)='›'"
                "    or contains(.,'Volgende') or contains(.,'Next')]",
                "//button[normalize-space(.)='»' or normalize-space(.)='›'"
                "        or contains(.,'Volgende')]",
                "//li[contains(@class,'next') and not(contains(@class,'disabled'))]//a",
            ]:
                try:
                    kandidaten = driver.find_elements(By.XPATH, sel)
                    for el in kandidaten:
                        if el.is_displayed() and el.is_enabled():
                            volgende = el
                            break
                except Exception:
                    pass
                if volgende:
                    break

        if not volgende:
            log.info(f"Geen volgende pagina na pagina {pagina} — klaar")
            break

        driver.execute_script("arguments[0].click();", volgende)
        pagina += 1
        time.sleep(2)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")

        leden = haal_leden_van_pagina(driver)
        nieuw = verwerk_batch(leden)
        log.info(f"Pagina {pagina}: {len(leden)} rijen, totaal uniek: {len(alle_leden)} (+{nieuw})")

        if nieuw == 0:
            log.info("Geen nieuwe leden op deze pagina — stoppen")
            break

    log.info(f"Paginering klaar: {pagina} pagina's, {len(alle_leden)} unieke leden")

    # Fallback: zoekfilter per letter als te weinig resultaten
    if len(alle_leden) < 10:
        log.warning(f"Slechts {len(alle_leden)} leden gevonden — probeer zoekfilter per letter")
        zoek_veld = None
        for sel in ["//input[@placeholder='Zoeken' or @type='search' or @type='text']"]:
            try:
                velden = driver.find_elements(By.XPATH, sel)
                for v in velden:
                    if v.is_displayed():
                        zoek_veld = v
                        break
            except Exception:
                pass

        if zoek_veld:
            for letter in "abcdefghijklmnopqrstuvwxyz":
                zoek_veld.clear()
                zoek_veld.send_keys(letter)
                time.sleep(1.5)
                leden = haal_leden_van_pagina(driver)
                nieuw = verwerk_batch(leden)
                log.info(f"  Filter '{letter}': {len(leden)} rijen, totaal: {len(alle_leden)} (+{nieuw})")
            zoek_veld.clear()

    screenshot(driver, "05_einde_scrape")
    return list(alle_leden.values())


def login_mijnknltb(driver) -> bool:
    """Login op mijnknltb.toernooi.nl met KNLTB-credentials."""
    log.info("Login op mijnknltb.toernooi.nl...")
    driver.get(f"{MIJNKNLTB_URL}/user/login")
    time.sleep(2)

    # Accepteer cookie-wall als die er is
    try:
        WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='Akkoord']"))
        ).click()
        time.sleep(1)
        log.info("Cookie-wall geaccepteerd")
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
        time.sleep(3)

        if "login" not in driver.current_url.lower():
            log.info(f"MijnKNLTB login geslaagd: {driver.current_url}")
            return True
        else:
            log.error(f"MijnKNLTB login mislukt: {driver.current_url}")
            screenshot(driver, "mijnknltb_login_fout")
            return False
    except Exception as e:
        log.error(f"MijnKNLTB login fout: {e}")
        screenshot(driver, "mijnknltb_login_fout")
        return False


def haal_padel_sterkte(driver, bondsnummer: str) -> dict:
    """
    Zoek speler op mijnknltb.toernooi.nl via bondsnummer en haal padel dubbel
    speelsterkte op. Geeft {'sterkte': '7', 'rating': '7,32'} of {} bij mislukking.
    """
    url = f"{MIJNKNLTB_URL}/find/player?q={bondsnummer}"
    driver.get(url)
    time.sleep(1.5)

    try:
        # Vind profiellink (niet eigen 'Mijn profiel'-link)
        profiel_links = driver.find_elements(
            By.XPATH,
            "//a[contains(@href,'player-profile') and "
            "not(normalize-space(.)='Mijn profiel')]"
        )
        if not profiel_links:
            log.warning(f"  Geen profiel gevonden voor {bondsnummer}")
            return {}

        profiel_url = profiel_links[0].get_attribute("href")
        driver.get(profiel_url)
        time.sleep(1.5)

        # Extraheer padel dubbel speelsterkte
        result = driver.execute_script("""
            var el = document.querySelector('span[title="Padel Dubbel"]');
            if (!el) return null;
            var sterkte = el.querySelector('.tag-duo__title');
            var rating  = el.querySelector('.tag-duo__value');
            return {
                sterkte: sterkte ? sterkte.textContent.trim() : null,
                rating:  rating  ? rating.textContent.trim()  : null
            };
        """)

        if result and result.get('sterkte'):
            log.info(f"  ✅ {bondsnummer}: sterkte={result['sterkte']}, rating={result['rating']}")
            return result
        else:
            log.info(f"  ⚠️  {bondsnummer}: geen padel sterkte op {profiel_url}")
            return {}

    except Exception as e:
        log.warning(f"  Fout bij ophalen padel sterkte {bondsnummer}: {e}")
        return {}


def main():
    if not BONDSNUMMER or not WACHTWOORD:
        log.error("Stel KNLTB_BONDSNUMMER en KNLTB_WACHTWOORD in als GitHub Secrets")
        sys.exit(1)

    driver = maak_driver()
    leden_lijst = []

    try:
        # Stap 1: etv-volley ledenlijst scrapen
        if not login(driver):
            log.error("Login etv-volley mislukt")
            sys.exit(1)

        if not naar_ledenlijst(driver):
            log.error("Navigatie naar Ledenlijst mislukt")
            sys.exit(1)

        leden_lijst = scrape_ledenlijst(driver)

        if not leden_lijst:
            log.error("Geen leden gevonden — leden.json wordt NIET overschreven")
            sys.exit(1)

        log.info(f"Ledenlijst: {len(leden_lijst)} leden gevonden")

        # Stap 2: mijnknltb.toernooi.nl — padel speelsterktes ophalen
        knltb_ok = login_mijnknltb(driver)
        if not knltb_ok:
            log.warning("MijnKNLTB login mislukt — speelsterktes worden overgeslagen")
        else:
            log.info(f"Padel speelsterktes ophalen voor {len(leden_lijst)} leden...")
            for i, lid in enumerate(leden_lijst):
                bnr = lid.get('bondsnummer', '').strip()
                if not bnr:
                    log.info(f"  [{i+1}/{len(leden_lijst)}] {lid['naam']}: geen bondsnummer, overgeslagen")
                    continue
                log.info(f"  [{i+1}/{len(leden_lijst)}] {lid['naam']} ({bnr})")
                sterkte_data = haal_padel_sterkte(driver, bnr)
                lid['sterkte_padel'] = sterkte_data.get('sterkte', '')
                lid['rating_padel']  = sterkte_data.get('rating', '')

    finally:
        try:
            screenshot(driver, "99_einde")
        except Exception:
            pass
        driver.quit()

    # Sorteer op naam en sla op
    leden_lijst.sort(key=lambda x: x['naam'])
    with open("leden.json", "w", encoding="utf-8") as f:
        json.dump(leden_lijst, f, ensure_ascii=False, indent=2)

    log.info(f"Opgeslagen: {len(leden_lijst)} leden in leden.json")
    log.info(f"Voorbeeld: {json.dumps(leden_lijst[0], ensure_ascii=False)}")
    met_sterkte = sum(1 for l in leden_lijst if l.get('sterkte_padel'))
    log.info(f"Padel sterkte aanwezig voor {met_sterkte}/{len(leden_lijst)} leden")


if __name__ == "__main__":
    main()

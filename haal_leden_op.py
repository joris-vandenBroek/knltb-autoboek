"""
Haal alle leden op van de Ledenlijst-pagina op etv-volley.nl
en sla op in leden.json.

Strategie:
1. Login via Selenium (UC + Xvfb, bypass Cloudflare)
2. Navigeer naar de Ledenlijst-tab
3. Scrape alle namen uit de HTML-tabel (eerste kolom)
4. Herhaal scrollen/paginering totdat er geen nieuwe namen meer bijkomen
5. Sla op in leden.json
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

LOGIN_URL   = "https://www.etv-volley.nl/mijn"
BONDSNUMMER = os.environ.get("KNLTB_BONDSNUMMER", "")
WACHTWOORD  = os.environ.get("KNLTB_WACHTWOORD", "")
TIMEOUT     = 20


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
    """Dunne wrapper rond etv_common.login() — gedeelde flow met
    lees_reserveringen.py (en op termijn ook boek_baan.py).
    """
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


def haal_namen_van_pagina(driver) -> list:
    """Extraheer namen uit de eerste kolom van de zichtbare tabel."""
    return driver.execute_script("""
        var namen = [];
        // Pak alle tabelrijen, sla headerrij over
        var rijen = document.querySelectorAll('table tr');
        rijen.forEach(function(rij) {
            var cellen = rij.querySelectorAll('td');
            if (!cellen.length) return;  // headerrij
            var naam = cellen[0].textContent.trim();
            if (naam && naam.length > 3 && naam.indexOf(' ') >= 0)
                namen.push(naam);
        });
        return namen;
    """) or []


def scrape_ledenlijst(driver) -> set:
    """
    Scrape alle namen uit de ledenlijst.
    Handelt infinite scroll, 'Toon meer'-knoppen en standaard paginering af.
    """
    alle_namen = set()

    # Wacht tot de tabel geladen is
    try:
        WebDriverWait(driver, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, "table tr td")) > 0
        )
        log.info("Tabel zichtbaar")
    except TimeoutException:
        log.warning("Tabel niet gevonden na 15s — toch proberen")

    screenshot(driver, "04_tabel_geladen")

    # Haal eerste batch namen op
    namen = haal_namen_van_pagina(driver)
    log.info(f"Eerste batch: {len(namen)} namen")
    alle_namen.update(namen)

    # Strategie 1: paginering — klik door alle pagina's heen
    # Aantal pagina's is variabel; stoppen zodra er geen volgende-knop meer is
    # of een pagina geen nieuwe namen oplevert.
    pagina = 1
    while True:
        volgende = None

        # Voorkeur: klik op het paginanummer pagina+1 (betrouwbaarder dan »)
        try:
            kandidaten = driver.find_elements(By.XPATH,
                f"//a[normalize-space(.)='{pagina + 1}']")
            for el in kandidaten:
                if el.is_displayed() and el.is_enabled():
                    volgende = el
                    break
        except Exception:
            pass

        # Fallback: zoek een "volgende pagina"-knop
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

        # Scroll kort zodat lazy-content laadt
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")

        namen = haal_namen_van_pagina(driver)
        nieuw = len(alle_namen)
        alle_namen.update(namen)
        log.info(f"Pagina {pagina}: {len(namen)} rijen, totaal uniek: {len(alle_namen)} (+{len(alle_namen)-nieuw})")

        if len(alle_namen) == nieuw:
            log.info("Geen nieuwe namen op deze pagina — stoppen")
            break

    log.info(f"Paginering klaar: {pagina} pagina's, {len(alle_namen)} unieke namen")

    # Strategie 3: zoekfilter gebruiken om leden per letter op te halen
    # (fallback als tabel gefilterd is of maar een beperkt aantal toont)
    if len(alle_namen) < 10:
        log.warning(f"Slechts {len(alle_namen)} namen gevonden — probeer zoekfilter per letter")
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
                namen = haal_namen_van_pagina(driver)
                alle_namen.update(namen)
                log.info(f"  Filter '{letter}': {len(namen)} namen, totaal: {len(alle_namen)}")
            zoek_veld.clear()

    screenshot(driver, "05_einde_scrape")
    return alle_namen


def main():
    if not BONDSNUMMER or not WACHTWOORD:
        log.error("Stel KNLTB_BONDSNUMMER en KNLTB_WACHTWOORD in als GitHub Secrets")
        sys.exit(1)

    driver = maak_driver()
    alle_namen = set()

    try:
        if not login(driver):
            log.error("Login mislukt")
            sys.exit(1)

        if not naar_ledenlijst(driver):
            log.error("Navigatie naar Ledenlijst mislukt")
            sys.exit(1)

        alle_namen = scrape_ledenlijst(driver)

    finally:
        try:
            screenshot(driver, "99_einde")
        except Exception:
            pass
        driver.quit()

    if not alle_namen:
        log.error("Geen leden gevonden — leden.json wordt NIET overschreven")
        sys.exit(1)

    gesorteerd = sorted(alle_namen)
    with open("leden.json", "w", encoding="utf-8") as f:
        json.dump(gesorteerd, f, ensure_ascii=False, indent=2)

    log.info(f"Opgeslagen: {len(gesorteerd)} leden in leden.json")
    log.info(f"Eerste 10: {gesorteerd[:10]}")


if __name__ == "__main__":
    main()

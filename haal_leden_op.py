"""
Haal alle leden op van de Ledenlijst-pagina op etv-volley.nl
en sla op in leden.json (naam + bondsnummer per lid).

Strategie:
1. Login via Selenium (UC + Xvfb, bypass Cloudflare)
2. Navigeer naar de Ledenlijst-tab
3. Scrape naam (kolom 0) + bondsnummer (kolom 1) uit de HTML-tabel
4. Herhaal paginering totdat er geen nieuwe leden meer bijkomen
5. Sla op in leden.json als lijst van objecten

Padel speelsterktes worden apart opgehaald door haal_padel_sterktes.py,
dat automatisch getriggerd wordt door haal_leden_op.yml na afloop.
"""

import os, sys, json, time, logging
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

LOGIN_URL   = "https://www.etv-volley.nl/mijn"
BONDSNUMMER = os.environ.get("KNLTB_BONDSNUMMER", "")
WACHTWOORD  = os.environ.get("KNLTB_WACHTWOORD", "")


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
    from etv_common import login as _common_login
    return _common_login(
        driver,
        bondsnummer=BONDSNUMMER,
        wachtwoord=WACHTWOORD,
        login_url=LOGIN_URL,
        screenshot=screenshot,
    )


def naar_ledenlijst(driver) -> bool:
    log.info("Navigeer naar Ledenlijst...")
    for sel in [
        "//a[contains(.,'Ledenlijst')]",
        "//a[contains(@href,'Member') or contains(@href,'Leden')]",
        "//*[@role='tab'][contains(.,'Ledenlijst')]",
    ]:
        try:
            link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, sel)))
            log.info(f"Ledenlijst-link: '{link.text.strip()}'")
            driver.execute_script("arguments[0].click();", link)
            time.sleep(3)
            screenshot(driver, "03_ledenlijst")
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
            if (!cellen.length) return;
            var naam = cellen[0].textContent.trim();
            var bondsnummer = cellen[1] ? cellen[1].textContent.trim() : '';
            if (naam && naam.length > 3 && naam.indexOf(' ') >= 0)
                leden.push({naam: naam, bondsnummer: bondsnummer});
        });
        return leden;
    """) or []


def scrape_ledenlijst(driver) -> list:
    """Scrape alle leden (naam + bondsnummer), handelt paginering af."""
    alle_leden = {}  # bondsnummer (of naam als fallback) -> object

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

    leden = haal_leden_van_pagina(driver)
    log.info(f"Eerste batch: {len(leden)} rijen, {verwerk_batch(leden)} nieuw")

    pagina = 1
    while True:
        volgende = None
        try:
            kandidaten = driver.find_elements(By.XPATH, f"//a[normalize-space(.)='{pagina + 1}']")
            for el in kandidaten:
                if el.is_displayed() and el.is_enabled():
                    volgende = el
                    break
        except Exception:
            pass

        if not volgende:
            for sel in [
                "//a[normalize-space(.)='»' or normalize-space(.)='›' or contains(.,'Volgende') or contains(.,'Next')]",
                "//button[normalize-space(.)='»' or normalize-space(.)='›' or contains(.,'Volgende')]",
                "//li[contains(@class,'next') and not(contains(@class,'disabled'))]//a",
            ]:
                try:
                    for el in driver.find_elements(By.XPATH, sel):
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
        log.info(f"Pagina {pagina}: {len(leden)} rijen, totaal: {len(alle_leden)} (+{nieuw})")
        if nieuw == 0:
            log.info("Geen nieuwe leden — stoppen")
            break

    log.info(f"Klaar: {pagina} pagina's, {len(alle_leden)} unieke leden")

    # Fallback: zoekfilter per letter als te weinig resultaten
    if len(alle_leden) < 10:
        log.warning(f"Slechts {len(alle_leden)} — probeer zoekfilter per letter")
        zoek_veld = None
        for sel in ["//input[@placeholder='Zoeken' or @type='search']"]:
            try:
                for v in driver.find_elements(By.XPATH, sel):
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
                nieuw = verwerk_batch(haal_leden_van_pagina(driver))
                log.info(f"  Filter '{letter}': totaal {len(alle_leden)} (+{nieuw})")
            zoek_veld.clear()

    screenshot(driver, "05_einde_scrape")
    return list(alle_leden.values())


def main():
    if not BONDSNUMMER or not WACHTWOORD:
        log.error("Stel KNLTB_BONDSNUMMER en KNLTB_WACHTWOORD in als GitHub Secrets")
        sys.exit(1)

    driver = maak_driver()
    leden_lijst = []

    try:
        if not login(driver):
            log.error("Login mislukt")
            sys.exit(1)
        if not naar_ledenlijst(driver):
            log.error("Navigatie naar Ledenlijst mislukt")
            sys.exit(1)
        leden_lijst = scrape_ledenlijst(driver)
    finally:
        try:
            screenshot(driver, "99_einde")
        except Exception:
            pass
        driver.quit()

    if not leden_lijst:
        log.error("Geen leden gevonden — leden.json wordt NIET overschreven")
        sys.exit(1)

    # Bewaar eventuele sterkte_padel uit huidige leden.json (zodat sterktes niet
    # verloren gaan als alleen de ledenlijst opnieuw gescraped wordt)
    bestaande_sterktes = {}
    try:
        with open("leden.json", encoding="utf-8") as f:
            oud = json.load(f)
        for item in oud:
            if isinstance(item, dict) and item.get('bondsnummer'):
                bestaande_sterktes[item['bondsnummer']] = {
                    'sterkte_padel': item.get('sterkte_padel', ''),
                    'rating_padel':  item.get('rating_padel', ''),
                }
        log.info(f"Bestaande sterktes bewaard voor {len(bestaande_sterktes)} leden")
    except Exception:
        pass

    for lid in leden_lijst:
        bnr = lid.get('bondsnummer', '')
        if bnr in bestaande_sterktes:
            lid['sterkte_padel'] = bestaande_sterktes[bnr]['sterkte_padel']
            lid['rating_padel']  = bestaande_sterktes[bnr]['rating_padel']
        else:
            lid.setdefault('sterkte_padel', '')
            lid.setdefault('rating_padel', '')

    leden_lijst.sort(key=lambda x: x['naam'])
    with open("leden.json", "w", encoding="utf-8") as f:
        json.dump(leden_lijst, f, ensure_ascii=False, indent=2)

    log.info(f"Opgeslagen: {len(leden_lijst)} leden in leden.json")
    log.info(f"Voorbeeld: {json.dumps(leden_lijst[0], ensure_ascii=False)}")


if __name__ == "__main__":
    main()

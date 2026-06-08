"""
Haal padel speelsterktes op van mijnknltb.toernooi.nl en voeg toe aan leden.json.

Strategie:
1. Lees leden.json (bevat naam + bondsnummer per lid)
2. Login op mijnknltb.toernooi.nl met KNLTB-credentials
3. Per lid: navigeer naar find/player?q={bondsnummer}
4. Klik eerste profiellink, extraheer 'Padel Dubbel' speelsterkte
5. Schrijf sterktes terug naar leden.json
"""

import os, sys, json, time, logging
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


def login_mijnknltb(driver) -> bool:
    """Login op mijnknltb.toernooi.nl."""
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


def haal_padel_sterkte(driver, bondsnummer: str) -> dict:
    """
    Zoek spelersprofiel via bondsnummer op mijnknltb.toernooi.nl.
    Geeft {'sterkte': '7', 'rating': '7,32'} of {} bij mislukking.
    """
    url = f"{MIJNKNLTB_URL}/find/player?q={bondsnummer}"
    driver.get(url)

    # Wacht tot zoekresultaten geladen zijn (max 5s)
    try:
        WebDriverWait(driver, 5).until(
            lambda d: len(d.find_elements(
                By.XPATH,
                "//a[contains(@href,'player-profile') and not(normalize-space(.)='Mijn profiel')]"
            )) > 0
        )
    except Exception:
        pass  # Geen resultaat — hieronder checken

    profiel_links = driver.find_elements(
        By.XPATH,
        "//a[contains(@href,'player-profile') and not(normalize-space(.)='Mijn profiel')]"
    )
    if not profiel_links:
        log.info(f"  Geen profiel gevonden voor {bondsnummer}")
        return {}

    profiel_url = profiel_links[0].get_attribute("href")
    driver.get(profiel_url)

    # Wacht op padel sterkte element
    try:
        WebDriverWait(driver, 5).until(
            lambda d: d.find_element(By.CSS_SELECTOR, 'span[title="Padel Dubbel"]')
        )
    except Exception:
        pass

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

    log.info(f"  ⚠️  {bondsnummer}: geen padel sterkte op {profiel_url}")
    screenshot(driver, f"geen_sterkte_{bondsnummer}")
    return {}


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

    # Normaliseer: oud string-formaat
    leden_lijst = [
        item if isinstance(item, dict) else {'naam': item, 'bondsnummer': ''}
        for item in leden_lijst
    ]

    met_bondsnummer = [l for l in leden_lijst if l.get('bondsnummer', '').strip()]
    log.info(f"{len(leden_lijst)} leden, {len(met_bondsnummer)} met bondsnummer")

    driver = maak_driver()
    try:
        if not login_mijnknltb(driver):
            log.error("Login mislukt — script stopt")
            sys.exit(1)

        for i, lid in enumerate(leden_lijst):
            bnr = lid.get('bondsnummer', '').strip()
            if not bnr:
                log.info(f"  [{i+1}/{len(leden_lijst)}] {lid['naam']}: geen bondsnummer")
                lid.setdefault('sterkte_padel', '')
                lid.setdefault('rating_padel', '')
                continue

            log.info(f"[{i+1}/{len(leden_lijst)}] {lid['naam']} ({bnr})")
            data = haal_padel_sterkte(driver, bnr)
            lid['sterkte_padel'] = data.get('sterkte', '')
            lid['rating_padel']  = data.get('rating', '')

    finally:
        try:
            screenshot(driver, "99_einde")
        except Exception:
            pass
        driver.quit()

    with open("leden.json", "w", encoding="utf-8") as f:
        json.dump(leden_lijst, f, ensure_ascii=False, indent=2)

    met_sterkte = sum(1 for l in leden_lijst if l.get('sterkte_padel'))
    log.info(f"Klaar: sterkte aanwezig voor {met_sterkte}/{len(leden_lijst)} leden")
    log.info(f"Opgeslagen in leden.json")


if __name__ == "__main__":
    main()

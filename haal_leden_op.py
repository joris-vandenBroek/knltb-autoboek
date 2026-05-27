"""
Haal alle leden op van etv-volley.nl en sla op in leden.json
Werkt door A-Z te zoeken in het spelerszoekvenster en alle autocomplete-suggesties te verzamelen.
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

LOGIN_URL     = "https://www.etv-volley.nl/mijn"
RESERVEER_URL = "https://www.etv-volley.nl/mijn/Reservations"
BONDSNUMMER   = os.environ.get("KNLTB_BONDSNUMMER", "")
WACHTWOORD    = os.environ.get("KNLTB_WACHTWOORD", "")
TIMEOUT       = 20

# Zoektermen: alle letters + veelvoorkomende tussenvoegsels
ZOEKTERMEN = list("abcdefghijklmnopqrstuvwxyz") + ["van ", "de ", "den ", "van de ", "van den "]


def screenshot(driver, naam):
    pad = f"{naam}.png"
    try:
        driver.save_screenshot(pad)
        log.info(f"📸 {pad} — URL: {driver.current_url}")
    except Exception as e:
        log.warning(f"Screenshot mislukt ({naam}): {e}")


def chrome_major_versie() -> int | None:
    """Detecteer de geïnstalleerde Chrome major versie zodat UC de juiste driver downloadt."""
    import subprocess, re
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
    log.warning("Chrome versie niet detecteerbaar — UC bepaalt zelf de driver versie")
    return None


def maak_driver():
    opties = uc.ChromeOptions()
    opties.add_argument("--no-sandbox")
    opties.add_argument("--disable-dev-shm-usage")
    opties.add_argument("--disable-gpu")
    opties.add_argument("--window-size=1280,900")
    opties.add_argument("--lang=nl-NL")
    # Geen --headless: draait via Xvfb zodat Cloudflare ons niet detecteert
    versie = chrome_major_versie()
    driver = uc.Chrome(options=opties, version_main=versie)
    driver.implicitly_wait(3)
    return driver


def login(driver) -> bool:
    log.info("Navigeer naar loginpagina...")
    driver.get(LOGIN_URL)
    time.sleep(5)
    screenshot(driver, "01_login")
    log.info(f"URL na navigatie: {driver.current_url}")

    # Controleer op ECHTE Cloudflare challenge (niet CDN-scripts die ook 'cloudflare' bevatten)
    page = driver.page_source.lower()
    if ("just a moment" in page or "checking your browser" in page
            or "cf-browser-verification" in page or "sorry, you have been blocked" in page):
        log.error("❌ Echte Cloudflare-blokkade gedetecteerd!")
        screenshot(driver, "01b_cloudflare")
        return False

    # Accepteer cookie-banner als die er is
    for sel in [
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accepteren')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accepteren')]",
    ]:
        try:
            knop = driver.find_element(By.XPATH, sel)
            knop.click()
            log.info("🍪 Cookie-banner geaccepteerd")
            time.sleep(2)
            break
        except Exception:
            pass

    # Als we op de homepage belandden (redirect van /mijn), zoek de login-link
    if "/mijn" not in driver.current_url:
        log.info(f"Geen /mijn in URL ({driver.current_url}), zoek login-link...")
        for sel in [
            "//a[contains(@href,'/mijn')]",
            "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mijn club')]",
            "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'inloggen')]",
            "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]",
        ]:
            try:
                link = driver.find_element(By.XPATH, sel)
                href = link.get_attribute('href') or ''
                log.info(f"Login-link gevonden: {href}")
                link.click()
                time.sleep(4)
                screenshot(driver, "01c_na_loginlink")
                break
            except Exception:
                pass

    log.info(f"URL vóór inlogvelden: {driver.current_url}")
    screenshot(driver, "01d_voor_inlogvelden")

    try:
        veld = WebDriverWait(driver, TIMEOUT).until(EC.element_to_be_clickable((By.XPATH,
            "//input[@type='text' or @type='email' or @name='username' or @name='Username' "
            "or @id='username' or @id='Username' "
            "or contains(@placeholder,'bondsnummer') or contains(@placeholder,'gebruikersnaam') "
            "or contains(@placeholder,'e-mail') or contains(@placeholder,'email')]")))
        veld.clear()
        veld.send_keys(BONDSNUMMER)
        log.info("Bondsnummer ingevuld")

        ww = WebDriverWait(driver, TIMEOUT).until(EC.element_to_be_clickable((By.XPATH,
            "//input[@type='password']")))
        ww.clear()
        ww.send_keys(WACHTWOORD)

        knop = WebDriverWait(driver, TIMEOUT).until(EC.element_to_be_clickable((By.XPATH,
            "//button[@type='submit'] | //input[@type='submit'] "
            "| //button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')] "
            "| //button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'inloggen')]")))
        knop.click()
        time.sleep(5)
        screenshot(driver, "02_na_login")
        log.info(f"URL na login-klik: {driver.current_url}")

        # Controleer of wachtwoordveld nog zichtbaar is = login mislukt
        try:
            pw_veld = driver.find_element(By.XPATH, "//input[@type='password']")
            if pw_veld.is_displayed():
                log.error("❌ Inloggen mislukt — wachtwoordveld nog zichtbaar na klik")
                # Log eventuele foutmeldingen op de pagina
                for sel in [
                    "//*[contains(@class,'error') or contains(@class,'alert') or contains(@class,'warning')]",
                    "//*[contains(text(),'onjuist') or contains(text(),'ongeldig') or contains(text(),'fout')]",
                ]:
                    try:
                        el = driver.find_element(By.XPATH, sel)
                        if el.text.strip():
                            log.error(f"   Foutmelding op pagina: {el.text.strip()[:200]}")
                    except Exception:
                        pass
                screenshot(driver, "02b_login_mislukt")
                return False
        except Exception:
            pass  # Geen wachtwoordveld meer zichtbaar = login geslaagd

        log.info(f"✅ Ingelogd — URL: {driver.current_url}")
        return True

    except TimeoutException as e:
        log.error(f"❌ Login timeout: {e}")
        log.error(f"   Huidige URL: {driver.current_url}")
        log.error(f"   Paginatitel: {driver.title}")
        screenshot(driver, "02_login_fout")
        return False


def naar_spelersselectie(driver) -> bool:
    """Navigeer naar de spelerszoek-stap via het boekingsproces."""
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
        log.error("❌ 'Baan afhangen' knop niet gevonden")
        # Log de volledige paginatitel en URL voor diagnose
        log.error(f"   Huidige URL: {driver.current_url}")
        log.error(f"   Paginatitel: {driver.title}")
        screenshot(driver, "03b_afhangen_fout")
        return False


def zoek_veld_ophalen(driver):
    try:
        veld = WebDriverWait(driver, 12).until(EC.element_to_be_clickable((By.XPATH,
            "//input[contains(@placeholder,'zoek') or contains(@placeholder,'naam') "
            "or contains(@placeholder,'speler') or contains(@class,'search') "
            "or contains(@id,'search') or contains(@id,'player')]")))
        log.info(f"✅ Zoekveld gevonden: placeholder='{veld.get_attribute('placeholder')}'")
        return veld
    except TimeoutException:
        log.error("❌ Zoekveld niet gevonden op pagina")
        screenshot(driver, "04b_zoekveld_fout")
        return None


def verzamel_suggesties(driver) -> set:
    """Haal alle zichtbare autocomplete-namen op."""
    namen = set()
    selectors = [
        "//ul[contains(@class,'suggestion') or contains(@class,'autocomplete') "
        "or contains(@class,'dropdown') or contains(@class,'result')]//li",
        "//div[contains(@class,'suggestion') or contains(@class,'autocomplete') "
        "or contains(@class,'dropdown') or contains(@class,'result')]"
        "//div[string-length(normalize-space(text()))>3]",
        "//li[contains(@class,'suggestion') or contains(@class,'autocomplete')]",
    ]
    for sel in selectors:
        try:
            for el in driver.find_elements(By.XPATH, sel):
                tekst = el.text.strip()
                if tekst and len(tekst) > 3 and " " in tekst:
                    namen.add(tekst)
        except Exception:
            pass
    return namen


def verzamel_recente_spelers(driver) -> set:
    namen = set()
    try:
        for el in driver.find_elements(By.XPATH,
                "//*[contains(@class,'recent')]//*[string-length(normalize-space(text()))>3]"):
            tekst = el.text.strip()
            if tekst and " " in tekst:
                namen.add(tekst)
    except Exception:
        pass
    return namen


def main():
    if not BONDSNUMMER or not WACHTWOORD:
        log.error("❌ Stel KNLTB_BONDSNUMMER en KNLTB_WACHTWOORD in als GitHub Secrets")
        sys.exit(1)

    driver = maak_driver()
    alle_namen = set()
    succes = False

    try:
        if not login(driver):
            log.error("Login mislukt — controleer screenshots voor diagnose")
            sys.exit(1)

        if not naar_spelersselectie(driver):
            log.error("Navigatie mislukt — controleer screenshots voor diagnose")
            sys.exit(1)

        # Recente spelers
        recente = verzamel_recente_spelers(driver)
        if recente:
            log.info(f"Recente spelers ({len(recente)}): {sorted(recente)[:5]}...")
            alle_namen.update(recente)

        zoek = zoek_veld_ophalen(driver)
        if not zoek:
            log.error("Zoekveld niet gevonden — controleer screenshot 04b")
            sys.exit(1)

        log.info(f"Start zoeken door {len(ZOEKTERMEN)} zoektermen...")
        for i, term in enumerate(ZOEKTERMEN):
            try:
                zoek.clear()
                zoek.send_keys(term)
                time.sleep(2.0)
                gevonden = verzamel_suggesties(driver)
                if gevonden:
                    log.info(f"  '{term}' → {len(gevonden)} namen")
                    alle_namen.update(gevonden)
                zoek.clear()
                time.sleep(0.4)

                # Tussentijdse screenshot elke 10 termen
                if (i + 1) % 10 == 0:
                    screenshot(driver, f"05_zoeken_{i+1}")

            except Exception as e:
                log.warning(f"Fout bij '{term}': {e}")
                screenshot(driver, f"fout_zoekterm_{term.strip()}")
                zoek = zoek_veld_ophalen(driver)
                if not zoek:
                    log.warning("Zoekveld kwijt — stoppen met zoeken")
                    break

        succes = True

    finally:
        screenshot(driver, "99_einde")
        driver.quit()

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

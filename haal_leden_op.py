"""
Haal alle leden op van etv-volley.nl en sla op in leden.json
Werkt door A-Z te zoeken in het spelerszoekvenster en alle autocomplete-suggesties te verzamelen.
"""

import os, sys, json, time, logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

LOGIN_URL    = "https://etv-volley.nl/mijn"
RESERVEER_URL = "https://etv-volley.nl/mijn/Reservations"
BONDSNUMMER  = os.environ.get("KNLTB_BONDSNUMMER", "")
WACHTWOORD   = os.environ.get("KNLTB_WACHTWOORD", "")
TIMEOUT      = 15

# Zoektermen: alle letters + veelvoorkomende Nederlandse voornaamletters/tussenvoegsel
ZOEKTERMEN = list("abcdefghijklmnopqrstuvwxyz") + ["van ", "de ", "den "]


def maak_driver():
    opties = Options()
    opties.add_argument("--headless")
    opties.add_argument("--no-sandbox")
    opties.add_argument("--disable-dev-shm-usage")
    opties.add_argument("--disable-gpu")
    opties.add_argument("--window-size=1280,900")
    driver = webdriver.Chrome(options=opties)
    driver.implicitly_wait(3)
    return driver


def login(driver):
    log.info("Inloggen...")
    driver.get(LOGIN_URL)
    time.sleep(3)
    try:
        veld = WebDriverWait(driver, TIMEOUT).until(EC.element_to_be_clickable((By.XPATH,
            "//input[@type='text' or @type='email' or @name='username' or @name='Username' "
            "or @id='username' or @id='Username' "
            "or contains(@placeholder,'bondsnummer') or contains(@placeholder,'gebruikersnaam') "
            "or contains(@placeholder,'e-mail') or contains(@placeholder,'email')]")))
        veld.clear(); veld.send_keys(BONDSNUMMER)
        ww = WebDriverWait(driver, TIMEOUT).until(EC.element_to_be_clickable((By.XPATH,
            "//input[@type='password']")))
        ww.clear(); ww.send_keys(WACHTWOORD)
        knop = WebDriverWait(driver, TIMEOUT).until(EC.element_to_be_clickable((By.XPATH,
            "//button[@type='submit'] | //input[@type='submit'] "
            "| //button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')] "
            "| //button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'inloggen')]")))
        knop.click()
        time.sleep(4)
        if "login" in driver.current_url.lower():
            log.error("Inloggen mislukt"); return False
        log.info("Ingelogd"); return True
    except TimeoutException as e:
        log.error(f"Inloggen fout: {e}"); return False


def naar_spelersselectie(driver):
    """Navigeer naar de spelerszoek-stap via het boekingsproces."""
    driver.get(RESERVEER_URL)
    time.sleep(2)
    try:
        knop = WebDriverWait(driver, TIMEOUT).until(EC.element_to_be_clickable((By.XPATH,
            "//a[contains(text(),'Baan afhangen') or contains(text(),'afhangen')] "
            "| //button[contains(text(),'Baan afhangen') or contains(text(),'afhangen')]")))
        knop.click()
        time.sleep(3)
        log.info("Spelersselectiepagina bereikt")
        return True
    except TimeoutException:
        log.error("'Baan afhangen' niet gevonden"); return False


def zoek_veld_ophalen(driver):
    try:
        return WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH,
            "//input[contains(@placeholder,'zoek') or contains(@placeholder,'naam') "
            "or contains(@placeholder,'speler') or contains(@class,'search')]")))
    except TimeoutException:
        return None


def verzamel_suggesties(driver):
    """Haal alle zichtbare autocomplete-namen op."""
    namen = set()
    selectors = [
        "//ul[contains(@class,'suggestion') or contains(@class,'autocomplete') "
        "or contains(@class,'dropdown') or contains(@class,'result')]//li",
        "//div[contains(@class,'suggestion') or contains(@class,'autocomplete') "
        "or contains(@class,'dropdown') or contains(@class,'result')]//div[string-length(normalize-space(text()))>3]",
        "//li[contains(@class,'suggestion') or contains(@class,'autocomplete')]",
    ]
    for sel in selectors:
        try:
            elementen = driver.find_elements(By.XPATH, sel)
            for el in elementen:
                tekst = el.text.strip()
                if tekst and len(tekst) > 3 and " " in tekst:
                    namen.add(tekst)
        except Exception:
            pass
    return namen


def verzamel_recente_spelers(driver):
    """Haal recent gespeelde spelers op (staan al zichtbaar op de pagina)."""
    namen = set()
    try:
        elementen = driver.find_elements(By.XPATH,
            "//*[contains(@class,'recent')]//*[string-length(normalize-space(text()))>3]")
        for el in elementen:
            tekst = el.text.strip()
            if tekst and " " in tekst:
                namen.add(tekst)
    except Exception:
        pass
    return namen


def main():
    if not BONDSNUMMER or not WACHTWOORD:
        log.error("Stel KNLTB_BONDSNUMMER en KNLTB_WACHTWOORD in"); sys.exit(1)

    driver = maak_driver()
    alle_namen = set()

    try:
        if not login(driver):
            sys.exit(1)
        if not naar_spelersselectie(driver):
            sys.exit(1)

        # Recente spelers meteen verzamelen
        recente = verzamel_recente_spelers(driver)
        if recente:
            log.info(f"Recente spelers: {recente}")
            alle_namen.update(recente)

        zoek = zoek_veld_ophalen(driver)
        if not zoek:
            log.error("Zoekveld niet gevonden"); sys.exit(1)

        for term in ZOEKTERMEN:
            try:
                zoek.clear()
                zoek.send_keys(term)
                time.sleep(1.8)
                gevonden = verzamel_suggesties(driver)
                if gevonden:
                    log.info(f"'{term}' → {len(gevonden)} namen")
                    alle_namen.update(gevonden)
                zoek.clear()
                time.sleep(0.3)
            except Exception as e:
                log.warning(f"Fout bij '{term}': {e}")
                zoek = zoek_veld_ophalen(driver)
                if not zoek:
                    break

    finally:
        driver.quit()

    gesorteerd = sorted(alle_namen)
    with open("leden.json", "w", encoding="utf-8") as f:
        json.dump(gesorteerd, f, ensure_ascii=False, indent=2)

    log.info(f"✅ {len(gesorteerd)} leden opgeslagen in leden.json")
    if gesorteerd:
        log.info(f"Eerste 5: {gesorteerd[:5]}")


if __name__ == "__main__":
    main()

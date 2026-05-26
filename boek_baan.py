"""
KNLTB Padelbaan Auto-Reservering
Automatisch een padelbaan reserveren via knltb.club

Omgevingsvariabelen (GitHub Secrets):
  KNLTB_BONDSNUMMER      - Jouw KNLTB bondsnummer
  KNLTB_WACHTWOORD       - Jouw KNLTB wachtwoord
  KNLTB_CLUB             - Naam van jouw club (bijv. "TC Amsterdam")
  GMAIL_ADRES            - Joris.vandenbroek@gmail.com
  GMAIL_APP_WACHTWOORD   - Gmail App-wachtwoord (myaccount.google.com → Beveiliging → App-wachtwoorden)
"""

import os
import sys
import time
import argparse
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# ── Instellingen ──────────────────────────────────────────────────────────────
KNLTB_URL            = "https://www.knltb.club/"
BONDSNUMMER          = os.environ.get("KNLTB_BONDSNUMMER", "")
WACHTWOORD           = os.environ.get("KNLTB_WACHTWOORD", "")
CLUB_NAAM            = os.environ.get("KNLTB_CLUB", "")
GMAIL_ADRES          = os.environ.get("GMAIL_ADRES", "Joris.vandenbroek@gmail.com")
GMAIL_APP_WACHTWOORD = os.environ.get("GMAIL_APP_WACHTWOORD", "")
SPELER1              = "Joris van den Broek"
BAAN_VOORKEUR        = [1, 2, 3, 4, 5, 6]
WACHT_TIMEOUT        = 15

def genereer_tijden(voorkeur_tijd: str) -> list[str]:
    """
    Genereer een lijst van tijden om te proberen, beginnend bij de voorkeur.
    Probeert eerst de gewenste tijd, dan steeds 30 min eerder/later afwisselend.
    Blijft binnen 08:00 – 22:00.
    Voorbeeld: voorkeur 10:00 → [10:00, 10:30, 09:30, 11:00, 09:00, 11:30, ...]
    """
    basis = datetime.strptime(voorkeur_tijd, "%H:%M")
    vroegst = datetime.strptime("08:00", "%H:%M")
    laatst  = datetime.strptime("22:00", "%H:%M")

    tijden = [basis]
    stap = 1
    while True:
        later   = basis + timedelta(minutes=30 * stap)
        eerder  = basis - timedelta(minutes=30 * stap)
        toegevoegd = False
        if later <= laatst:
            tijden.append(later)
            toegevoegd = True
        if eerder >= vroegst:
            tijden.append(eerder)
            toegevoegd = True
        if not toegevoegd:
            break
        stap += 1

    return [t.strftime("%H:%M") for t in tijden]
# ─────────────────────────────────────────────────────────────────────────────


def stuur_email(onderwerp: str, inhoud: str):
    """Stuur een e-mail via Gmail SMTP."""
    if not GMAIL_ADRES or not GMAIL_APP_WACHTWOORD:
        log.warning("Gmail niet ingesteld — e-mail overgeslagen.")
        return
    try:
        bericht = MIMEMultipart()
        bericht["From"]    = GMAIL_ADRES
        bericht["To"]      = GMAIL_ADRES
        bericht["Subject"] = onderwerp
        bericht.attach(MIMEText(inhoud, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADRES, GMAIL_APP_WACHTWOORD)
            server.send_message(bericht)
        log.info(f"📧 E-mail verstuurd: {onderwerp}")
    except Exception as e:
        log.error(f"❌ E-mail versturen mislukt: {e}")


def maak_driver() -> webdriver.Chrome:
    opties = Options()
    opties.add_argument("--headless")
    opties.add_argument("--no-sandbox")
    opties.add_argument("--disable-dev-shm-usage")
    opties.add_argument("--disable-gpu")
    opties.add_argument("--window-size=1280,900")
    opties.add_argument("--lang=nl-NL")
    driver = webdriver.Chrome(options=opties)
    driver.implicitly_wait(5)
    return driver


def wacht_op(driver, by, waarde, timeout=WACHT_TIMEOUT):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, waarde))
    )


def login(driver: webdriver.Chrome) -> bool:
    log.info("Navigeer naar KNLTB Club...")
    driver.get(KNLTB_URL)
    time.sleep(2)
    try:
        login_knop = wacht_op(driver, By.XPATH,
            "//a[contains(text(),'Inloggen') or contains(text(),'Login') or contains(@href,'login')]")
        login_knop.click()
        time.sleep(1)

        if CLUB_NAAM:
            log.info(f"Club selecteren: {CLUB_NAAM}")
            club_veld = wacht_op(driver, By.XPATH,
                "//input[contains(@placeholder,'club') or contains(@name,'club')]")
            club_veld.clear()
            club_veld.send_keys(CLUB_NAAM)
            time.sleep(1)
            suggestie = wacht_op(driver, By.XPATH,
                "//ul[contains(@class,'suggest')]//li[1] | //div[contains(@class,'autocomplete')]//div[1]")
            suggestie.click()
            time.sleep(1)

        bond_veld = wacht_op(driver, By.XPATH,
            "//input[@type='text' or @name='username' or @id='username' or contains(@placeholder,'bondsnummer')]")
        bond_veld.clear()
        bond_veld.send_keys(BONDSNUMMER)

        ww_veld = wacht_op(driver, By.XPATH, "//input[@type='password']")
        ww_veld.clear()
        ww_veld.send_keys(WACHTWOORD)
        ww_veld.send_keys(Keys.RETURN)
        time.sleep(3)

        log.info("✅ Ingelogd!")
        return True
    except TimeoutException as e:
        log.error(f"❌ Inloggen mislukt: {e}")
        driver.save_screenshot("login_fout.png")
        return False


def ga_naar_baan_reserveren(driver: webdriver.Chrome, datum: str) -> bool:
    log.info(f"Navigeer naar baan reserveren voor {datum}...")
    try:
        spelen = wacht_op(driver, By.XPATH,
            "//a[contains(text(),'Spelen') or contains(text(),'Baan reserveren') or contains(@href,'spelen')]")
        spelen.click()
        time.sleep(2)

        doel_datum = datetime.strptime(datum, "%Y-%m-%d")
        try:
            kalender = wacht_op(driver, By.XPATH,
                "//button[contains(@class,'calendar') or contains(@aria-label,'datum') or contains(@class,'date')]")
            kalender.click()
            time.sleep(1)
            dag_str = str(doel_datum.day)
            dag_cel = wacht_op(driver, By.XPATH,
                f"//td[normalize-space(text())='{dag_str}' and not(contains(@class,'disabled'))]")
            dag_cel.click()
            time.sleep(1)
        except TimeoutException:
            log.warning("Kalender niet gevonden, probeer URL-navigatie...")

        log.info(f"✅ Op juiste datum: {datum}")
        return True
    except TimeoutException as e:
        log.error(f"❌ Navigatie mislukt: {e}")
        driver.save_screenshot("navigatie_fout.png")
        return False


def probeer_reservering(driver: webdriver.Chrome, baan_nr: int, tijd: str,
                        speler2: str, speler3: str, speler4: str) -> bool:
    """Probeer één specifieke baan op één specifiek tijdstip te boeken."""
    try:
        plus_knop = driver.find_element(By.XPATH,
            f"//*[contains(text(),'Padelbaan {baan_nr}') or contains(text(),'Padel {baan_nr}') or "
            f"contains(@data-baan,'{baan_nr}')]"
            f"//ancestor::tr//td[contains(@data-tijd,'{tijd}')]//button[contains(@class,'plus') or "
            f"contains(@class,'available') or contains(@aria-label,'reserveer')]"
        )
        plus_knop.click()
        time.sleep(2)

        for i, speler in enumerate([speler2, speler3, speler4], start=2):
            toevoeg_knop = wacht_op(driver, By.XPATH,
                "//button[contains(text(),'speler toevoegen') or contains(text(),'Toevoegen')]")
            toevoeg_knop.click()
            time.sleep(1)
            zoek_veld = wacht_op(driver, By.XPATH,
                "//input[contains(@placeholder,'naam') or contains(@placeholder,'zoek') or "
                "contains(@placeholder,'speler')]")
            zoek_veld.clear()
            zoek_veld.send_keys(speler)
            time.sleep(2)
            resultaat = wacht_op(driver, By.XPATH,
                f"//li[contains(text(),'{speler.split()[0]}')]"
                f" | //div[contains(@class,'result')][contains(text(),'{speler.split()[0]}')]")
            resultaat.click()
            time.sleep(1)

        bevestig = wacht_op(driver, By.XPATH,
            "//button[contains(text(),'Reserveren') or contains(text(),'Bevestigen') or contains(text(),'Boeken')]")
        bevestig.click()
        time.sleep(3)
        return True

    except (NoSuchElementException, TimeoutException):
        return False


def reserveer_baan(driver: webdriver.Chrome, datum: str, voorkeur_tijd: str,
                   speler2: str, speler3: str, speler4: str) -> tuple[int, str]:
    """
    Probeer alle tijden (rondom voorkeur) × alle banen (1-6).
    Geeft (baannummer, geboekte_tijd) terug bij succes, anders (0, "").
    """
    tijden = genereer_tijden(voorkeur_tijd)
    log.info(f"Tijden om te proberen: {tijden}")

    for tijd in tijden:
        log.info(f"── Probeer tijdslot {tijd} ──")
        for baan_nr in BAAN_VOORKEUR:
            log.info(f"   Padelbaan {baan_nr} om {tijd}...")
            if probeer_reservering(driver, baan_nr, tijd, speler2, speler3, speler4):
                log.info(f"🎾 GESLAAGD! Padelbaan {baan_nr} op {datum} om {tijd}")
                return baan_nr, tijd
            log.info(f"   → Niet beschikbaar")

    log.error("❌ Geen enkele combinatie van tijd + baan beschikbaar!")
    driver.save_screenshot("geen_baan_beschikbaar.png")
    return 0, ""


def main():
    parser = argparse.ArgumentParser(description="KNLTB Padelbaan Auto-Reservering")
    parser.add_argument("--datum",   required=True)
    parser.add_argument("--tijd",    required=True)
    parser.add_argument("--speler2", required=True)
    parser.add_argument("--speler3", required=True)
    parser.add_argument("--speler4", required=True)
    args = parser.parse_args()

    if not BONDSNUMMER or not WACHTWOORD:
        log.error("❌ Stel KNLTB_BONDSNUMMER en KNLTB_WACHTWOORD in als GitHub Secrets!")
        sys.exit(1)

    try:
        datetime.strptime(args.datum, "%Y-%m-%d")
    except ValueError:
        log.error("❌ Datum moet YYYY-MM-DD zijn")
        sys.exit(1)

    log.info("=" * 50)
    log.info("🎾 KNLTB Padelbaan Auto-Reservering")
    log.info(f"   Datum:         {args.datum}")
    log.info(f"   Voorkeurstijd: {args.tijd}")
    log.info(f"   Spelers:       {SPELER1}, {args.speler2}, {args.speler3}, {args.speler4}")
    log.info("=" * 50)

    driver = maak_driver()
    baan_nr, geboekte_tijd = 0, ""
    try:
        if not login(driver):
            stuur_email(
                "❌ KNLTB: Inloggen mislukt",
                f"Automatisch reserveren op {args.datum} mislukt — kon niet inloggen.\n"
                f"Log in zelf via de KNLTB app!"
            )
            sys.exit(1)

        if not ga_naar_baan_reserveren(driver, args.datum):
            stuur_email(
                "❌ KNLTB: Navigatie mislukt",
                f"Automatisch reserveren op {args.datum} mislukt — navigatie fout.\n"
                f"Log in zelf via de KNLTB app!"
            )
            sys.exit(1)

        baan_nr, geboekte_tijd = reserveer_baan(
            driver, args.datum, args.tijd,
            args.speler2, args.speler3, args.speler4
        )
    finally:
        driver.quit()

    datum_nl = datetime.strptime(args.datum, "%Y-%m-%d").strftime("%d-%m-%Y")

    if baan_nr == 0:
        stuur_email(
            f"❌ KNLTB: Geen baan beschikbaar op {datum_nl}",
            f"Geen enkele padelbaan (1-6) was beschikbaar op {datum_nl},\n"
            f"ook niet op andere tijden rondom {args.tijd}.\n\n"
            f"Probeer zelf handmatig te reserveren via de KNLTB app."
        )
        sys.exit(1)
    else:
        tijdsverschil = "" if geboekte_tijd == args.tijd else f" (voorkeur was {args.tijd})"
        stuur_email(
            f"KNLTB GEBOEKT: Padelbaan {baan_nr} – {datum_nl} om {geboekte_tijd}",
            f"✅ Padelbaan succesvol gereserveerd!\n\n"
            f"🎾 Padelbaan:  {baan_nr}\n"
            f"📅 Datum:      {datum_nl}\n"
            f"🕐 Tijd:       {geboekte_tijd} – 60 min{tijdsverschil}\n"
            f"👥 Spelers:\n"
            f"   1. {SPELER1}\n"
            f"   2. {args.speler2}\n"
            f"   3. {args.speler3}\n"
            f"   4. {args.speler4}\n\n"
            f"Zeg tegen Claude: \"Padelbaan {baan_nr} om {geboekte_tijd} is geboekt\""
            f" om je agenda bij te werken."
        )
        log.info("✅ Klaar!")


if __name__ == "__main__":
    main()

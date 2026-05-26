"""
ETV Volley Padelbaan Auto-Reservering
Automatisch een padelbaan reserveren via etv-volley.nl/mijn

Omgevingsvariabelen (GitHub Secrets):
  KNLTB_BONDSNUMMER      - Jouw bondsnummer / gebruikersnaam
  KNLTB_WACHTWOORD       - Jouw wachtwoord
  GMAIL_ADRES            - Joris.vandenbroek@gmail.com
  GMAIL_APP_WACHTWOORD   - Gmail App-wachtwoord
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
BASE_URL             = "https://etv-volley.nl/mijn"
LOGIN_URL            = "https://etv-volley.nl/mijn"
RESERVEER_URL        = "https://etv-volley.nl/mijn/Reservations"
SPELERS_URL          = "https://etv-volley.nl/mijn/ReservationsPlayers"
DAG_URL              = "https://etv-volley.nl/mijn/ReservationsDay"
BAAN_URL             = "https://etv-volley.nl/mijn/ReservationsCourt"

BONDSNUMMER          = os.environ.get("KNLTB_BONDSNUMMER", "")
WACHTWOORD           = os.environ.get("KNLTB_WACHTWOORD", "")
GMAIL_ADRES          = os.environ.get("GMAIL_ADRES", "Joris.vandenbroek@gmail.com")
GMAIL_APP_WACHTWOORD = os.environ.get("GMAIL_APP_WACHTWOORD", "")
SPELER1              = "Joris van den Broek"

# Padelbanen op etv-volley.nl (rijnummers 9-14 = Padel 1-6)
PADEL_BANEN          = ["Padel 1", "Padel 2", "Padel 3", "Padel 4", "Padel 5", "Padel 6"]
WACHT_TIMEOUT        = 15
# ─────────────────────────────────────────────────────────────────────────────


def genereer_tijden(voorkeur_tijd: str) -> list:
    """Genereer tijden rondom voorkeur, 30 min stappen, tussen 08:00 en 22:00."""
    basis   = datetime.strptime(voorkeur_tijd, "%H:%M")
    vroegst = datetime.strptime("08:00", "%H:%M")
    laatst  = datetime.strptime("22:00", "%H:%M")
    tijden  = [basis]
    stap = 1
    while True:
        later  = basis + timedelta(minutes=30 * stap)
        eerder = basis - timedelta(minutes=30 * stap)
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


def dagdeel(tijd: str) -> str:
    """Bepaal dagdeel op basis van tijd."""
    uur = int(tijd.split(":")[0])
    if uur < 12:
        return "Ochtend"
    elif uur < 17:
        return "Middag"
    else:
        return "Avond"


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


def screenshot(driver, naam):
    driver.save_screenshot(f"{naam}.png")
    log.info(f"📸 Screenshot: {naam}.png | URL: {driver.current_url}")


# ── STAP 1: Inloggen ──────────────────────────────────────────────────────────
def login(driver: webdriver.Chrome) -> bool:
    log.info(f"Navigeer naar {LOGIN_URL}")
    driver.get(LOGIN_URL)
    time.sleep(3)
    screenshot(driver, "01_login_pagina")

    try:
        gebruiker_veld = wacht_op(driver, By.XPATH,
            "//input[@type='text' or @type='email' "
            "or @name='username' or @name='Username' or @name='UserName' "
            "or @id='username' or @id='Username' or @id='UserName' "
            "or contains(@placeholder,'bondsnummer') or contains(@placeholder,'gebruikersnaam') "
            "or contains(@placeholder,'e-mail') or contains(@placeholder,'email')]")
        gebruiker_veld.clear()
        gebruiker_veld.send_keys(BONDSNUMMER)

        ww_veld = wacht_op(driver, By.XPATH, "//input[@type='password']")
        ww_veld.clear()
        ww_veld.send_keys(WACHTWOORD)

        inlog_knop = wacht_op(driver, By.XPATH,
            "//button[@type='submit'] | //input[@type='submit'] "
            "| //button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')] "
            "| //button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'inloggen')]")
        inlog_knop.click()
        time.sleep(4)
        screenshot(driver, "02_na_login")

        if "login" in driver.current_url.lower() or "signin" in driver.current_url.lower():
            log.error("❌ Inloggen mislukt — nog steeds op loginpagina")
            return False

        log.info("✅ Ingelogd!")
        return True
    except TimeoutException as e:
        log.error(f"❌ Inloggen mislukt: {e}")
        screenshot(driver, "login_fout")
        return False


# ── STAP 2: Baan afhangen klikken ────────────────────────────────────────────
def klik_baan_afhangen(driver: webdriver.Chrome) -> bool:
    log.info("Navigeer naar reserveringspagina...")
    driver.get(RESERVEER_URL)
    time.sleep(2)
    screenshot(driver, "03_reserveer_pagina")

    try:
        afhangen_knop = wacht_op(driver, By.XPATH,
            "//a[contains(text(),'Baan afhangen') or contains(text(),'afhangen')] "
            "| //button[contains(text(),'Baan afhangen') or contains(text(),'afhangen')]")
        afhangen_knop.click()
        time.sleep(2)
        screenshot(driver, "04_na_afhangen_klik")
        log.info("✅ 'Baan afhangen' geklikt")
        return True
    except TimeoutException as e:
        log.error(f"❌ 'Baan afhangen' knop niet gevonden: {e}")
        screenshot(driver, "afhangen_fout")
        return False


# ── STAP 3: Spelers toevoegen ─────────────────────────────────────────────────
def voeg_spelers_toe(driver: webdriver.Chrome, speler2: str, speler3: str, speler4: str) -> bool:
    log.info("Spelers toevoegen...")
    time.sleep(2)
    screenshot(driver, "05_spelers_pagina")

    for speler in [speler2, speler3, speler4]:
        log.info(f"Speler toevoegen: {speler}")

        # Altijd via zoekbalk
        try:
            zoek_veld = wacht_op(driver, By.XPATH,
                "//input[contains(@placeholder,'zoek') or contains(@placeholder,'naam') "
                "or contains(@placeholder,'speler') or contains(@class,'search')]")
            zoek_veld.clear()
            zoek_veld.send_keys(speler.split()[0])  # Voornaam
            time.sleep(2)

            # Klik suggestie die achternaam bevat
            suggestie = wacht_op(driver, By.XPATH,
                f"//li[contains(text(),'{speler.split()[-1]}')]"
                f" | //div[contains(@class,'suggestion') or contains(@class,'autocomplete')"
                f" or contains(@class,'dropdown') or contains(@class,'result')]"
                f"[contains(text(),'{speler.split()[-1]}')]")
            suggestie.click()
            time.sleep(1)
            log.info(f"  ✅ {speler} toegevoegd")
        except TimeoutException:
            log.error(f"  ❌ {speler} niet gevonden!")
            return False

    screenshot(driver, "06_spelers_toegevoegd")

    # Klik Volgende
    try:
        volgende = wacht_op(driver, By.XPATH,
            "//button[contains(text(),'Volgende') or contains(text(),'Next')] "
            "| //a[contains(text(),'Volgende')]")
        volgende.click()
        time.sleep(2)
        log.info("✅ Spelers toegevoegd, naar dagkeuze")
        return True
    except TimeoutException:
        log.error("❌ 'Volgende' knop niet gevonden na spelers")
        screenshot(driver, "volgende_fout_spelers")
        return False


# ── STAP 4: Dag en dagdeel kiezen ────────────────────────────────────────────
def kies_dag(driver: webdriver.Chrome, datum: str, tijd: str) -> bool:
    log.info(f"Dag kiezen: {datum}, dagdeel: {dagdeel(tijd)}")
    time.sleep(2)
    screenshot(driver, "07_dag_pagina")

    doel_datum = datetime.strptime(datum, "%Y-%m-%d")
    dag_nr     = str(doel_datum.day)
    maand_kort = doel_datum.strftime("%b").lower()  # bijv. "mei"
    gewenst_dagdeel = dagdeel(tijd)

    try:
        # Klik op de juiste dag
        dag_cel = wacht_op(driver, By.XPATH,
            f"//td[contains(text(),'{dag_nr}')] "
            f"| //*[contains(@class,'day') and contains(text(),'{dag_nr}')] "
            f"| //*[contains(text(),'{dag_nr}') and contains(text(),'{doel_datum.strftime('%b')}')]")
        dag_cel.click()
        time.sleep(1)
        log.info(f"✅ Dag {dag_nr} geklikt")
    except TimeoutException:
        log.error(f"❌ Dag {dag_nr} niet gevonden")
        screenshot(driver, "dag_fout")
        return False

    try:
        # Klik op het juiste dagdeel
        dagdeel_knop = wacht_op(driver, By.XPATH,
            f"//*[contains(text(),'{gewenst_dagdeel}') and not(contains(@class,'disabled'))]")
        dagdeel_knop.click()
        time.sleep(1)
        log.info(f"✅ Dagdeel '{gewenst_dagdeel}' geklikt")
    except TimeoutException:
        log.error(f"❌ Dagdeel '{gewenst_dagdeel}' niet gevonden")
        screenshot(driver, "dagdeel_fout")
        return False

    screenshot(driver, "08_dag_geselecteerd")

    # Klik Volgende
    try:
        volgende = wacht_op(driver, By.XPATH,
            "//button[contains(text(),'Volgende') or contains(text(),'Next')] "
            "| //a[contains(text(),'Volgende')]")
        volgende.click()
        time.sleep(2)
        log.info("✅ Naar baankeuze")
        return True
    except TimeoutException:
        log.error("❌ 'Volgende' knop niet gevonden na dag")
        screenshot(driver, "volgende_fout_dag")
        return False


# ── STAP 5: Baan en tijd kiezen ──────────────────────────────────────────────
def kies_baan_en_tijd(driver: webdriver.Chrome, voorkeur_tijd: str) -> tuple:
    """
    Kies een beschikbare padelbaan op de voorkeurstijd (of alternatief).
    Geeft (baannaam, geboekte_tijd) terug bij succes, anders ("", "").
    """
    log.info("Baankeuze pagina...")
    time.sleep(2)
    screenshot(driver, "09_baan_pagina")

    tijden = genereer_tijden(voorkeur_tijd)
    log.info(f"Tijden om te proberen: {tijden}")

    for tijd in tijden:
        for baan in PADEL_BANEN:
            log.info(f"Probeer {baan} om {tijd}...")
            try:
                # Zoek tijdknop in de rij van de gewenste padelbaan
                tijdknop = driver.find_element(By.XPATH,
                    f"//*[contains(text(),'{baan}')]"
                    f"/ancestor::tr"
                    f"//td[normalize-space(text())='{tijd}'] "
                    f"| //*[contains(text(),'{baan}')]"
                    f"/ancestor::*[contains(@class,'row') or contains(@class,'baan')]"
                    f"//*[normalize-space(text())='{tijd}']")
                tijdknop.click()
                time.sleep(2)
                log.info(f"✅ {baan} om {tijd} geselecteerd!")
                screenshot(driver, f"10_baan_geselecteerd")
                return baan, tijd
            except NoSuchElementException:
                continue

    log.error("❌ Geen beschikbare padelbaan/tijd gevonden!")
    screenshot(driver, "baan_fout")
    return "", ""


# ── STAP 6: Bevestigen ────────────────────────────────────────────────────────
def bevestig(driver: webdriver.Chrome) -> bool:
    log.info("Bevestigen...")
    try:
        # Eerst Volgende
        volgende = wacht_op(driver, By.XPATH,
            "//button[contains(text(),'Volgende') or contains(text(),'Next')] "
            "| //a[contains(text(),'Volgende')]")
        volgende.click()
        time.sleep(2)
        screenshot(driver, "11_bevestig_pagina")

        # Dan Bevestigen
        bevestig_knop = wacht_op(driver, By.XPATH,
            "//button[contains(text(),'Bevestig') or contains(text(),'Confirm') or contains(text(),'Boek')] "
            "| //a[contains(text(),'Bevestig')]")
        bevestig_knop.click()
        time.sleep(3)
        screenshot(driver, "12_na_bevestiging")
        log.info("✅ Bevestigd!")
        return True
    except TimeoutException as e:
        log.error(f"❌ Bevestigen mislukt: {e}")
        screenshot(driver, "bevestig_fout")
        return False


# ── Naamcheck ─────────────────────────────────────────────────────────────────
def zoek_speler(driver: webdriver.Chrome, naam: str) -> bool:
    """Controleer of een speler gevonden kan worden op de spelersselectiepagina."""
    try:
        zoek_veld = wacht_op(driver, By.XPATH,
            "//input[contains(@placeholder,'zoek') or contains(@placeholder,'naam') "
            "or contains(@placeholder,'speler') or contains(@class,'search')]",
            timeout=8)
        zoek_veld.clear()
        zoek_veld.send_keys(naam.split()[0])
        time.sleep(2)

        resultaten = driver.find_elements(By.XPATH,
            f"//*[contains(text(),'{naam.split()[-1]}')]"
            f"[ancestor::*[contains(@class,'suggestion') or contains(@class,'autocomplete') "
            f"or contains(@class,'dropdown') or contains(@class,'result')]]")

        # Ook checken in recent gespeeld
        recent = driver.find_elements(By.XPATH,
            f"//*[contains(@class,'recent')]//*[contains(text(),'{naam.split()[0]}')]"
            f"[contains(text(),'{naam.split()[-1]}') or "
            f"following::*[contains(text(),'{naam.split()[-1]}')]]")

        gevonden = len(resultaten) > 0 or len(recent) > 0

        # Reset zoekveld
        zoek_veld.clear()
        return gevonden
    except TimeoutException:
        return False


def main_check_namen(args):
    """Controleer of alle spelersnamen gevonden worden."""
    log.info("=" * 50)
    log.info("🔍 NAAMCHECK")
    log.info("=" * 50)

    driver = maak_driver()
    resultaten = {}

    try:
        if not login(driver):
            for naam in [args.speler2, args.speler3, args.speler4]:
                resultaten[naam] = None
        else:
            # Ga naar spelersselectie
            if klik_baan_afhangen(driver):
                time.sleep(2)
                for naam in [args.speler2, args.speler3, args.speler4]:
                    gevonden = zoek_speler(driver, naam)
                    resultaten[naam] = gevonden
                    log.info(f"  {'✅' if gevonden else '❌'} {naam}")
            else:
                for naam in [args.speler2, args.speler3, args.speler4]:
                    resultaten[naam] = None
    finally:
        driver.quit()

    niet_gevonden = [n for n, ok in resultaten.items() if not ok]
    gevonden      = [n for n, ok in resultaten.items() if ok]

    print("\n── NAAMCHECK RESULTAAT ──")
    for naam in gevonden:      print(f"✅ {naam}")
    for naam in niet_gevonden: print(f"❌ {naam}")

    if niet_gevonden:
        with open("namen_niet_gevonden.txt", "w") as f:
            f.write("\n".join(niet_gevonden))
        stuur_email(
            "⚠️ KNLTB: Spelernaam niet gevonden",
            f"Niet gevonden:\n" + "\n".join(f"  ❌ {n}" for n in niet_gevonden)
            + f"\n\nWel gevonden:\n" + "\n".join(f"  ✅ {n}" for n in gevonden)
            + f"\n\nCorrigeer de naam(en) en geef de opdracht opnieuw aan Claude."
        )
        sys.exit(1)
    else:
        print("\n✅ Alle spelers gevonden!")
        sys.exit(0)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-namen", action="store_true")
    parser.add_argument("--datum",   required=False)
    parser.add_argument("--tijd",    required=False)
    parser.add_argument("--speler2", required=True)
    parser.add_argument("--speler3", required=True)
    parser.add_argument("--speler4", required=True)
    args = parser.parse_args()

    if args.check_namen:
        main_check_namen(args)
        return

    if not args.datum or not args.tijd:
        log.error("❌ --datum en --tijd zijn verplicht")
        sys.exit(1)

    if not BONDSNUMMER or not WACHTWOORD:
        log.error("❌ Stel KNLTB_BONDSNUMMER en KNLTB_WACHTWOORD in als GitHub Secrets!")
        sys.exit(1)

    try:
        speeldatum = datetime.strptime(args.datum, "%Y-%m-%d")
    except ValueError:
        log.error("❌ Datum moet YYYY-MM-DD zijn")
        sys.exit(1)

    # 48-uurs check
    speelmoment     = datetime.combine(speeldatum.date(), datetime.strptime(args.tijd, "%H:%M").time())
    uren_tot_spelen = (speelmoment - datetime.now()).total_seconds() / 3600
    log.info(f"⏱️  Uren tot speelmoment: {uren_tot_spelen:.1f}")

    if uren_tot_spelen >= 48:
        boekingsdatum = speeldatum - timedelta(days=2)
        nu = datetime.now()
        if nu.date() < boekingsdatum.date():
            log.info(f"📅 Boekingsdatum is {boekingsdatum.strftime('%d-%m-%Y')} om 07:00 — script stopt.")
            sys.exit(0)
        elif nu.date() == boekingsdatum.date() and nu.hour < 7:
            wacht_sec = int((boekingsdatum.replace(hour=7, minute=0, second=0) - nu).total_seconds())
            log.info(f"⏳ Wacht {wacht_sec // 60} min tot 07:00...")
            time.sleep(wacht_sec)
        else:
            log.info("✅ Boekingsdatum en na 07:00 — direct boeken!")
    else:
        log.info("⚡ Minder dan 48 uur — direct boeken!")

    log.info("=" * 50)
    log.info("🎾 ETV Volley Padelbaan Auto-Reservering")
    log.info(f"   Datum:   {args.datum}")
    log.info(f"   Tijd:    {args.tijd}")
    log.info(f"   Spelers: {SPELER1}, {args.speler2}, {args.speler3}, {args.speler4}")
    log.info("=" * 50)

    driver = maak_driver()
    baan, geboekte_tijd = "", ""

    try:
        if not login(driver):
            stuur_email("❌ ETV Volley: Inloggen mislukt",
                f"Automatisch reserveren op {args.datum} mislukt — kon niet inloggen.")
            sys.exit(1)

        if not klik_baan_afhangen(driver):
            stuur_email("❌ ETV Volley: Navigatie mislukt",
                f"Kon 'Baan afhangen' niet vinden op {args.datum}.")
            sys.exit(1)

        if not voeg_spelers_toe(driver, args.speler2, args.speler3, args.speler4):
            stuur_email("❌ ETV Volley: Speler niet gevonden",
                f"Een speler kon niet worden toegevoegd op {args.datum}.")
            sys.exit(1)

        if not kies_dag(driver, args.datum, args.tijd):
            stuur_email("❌ ETV Volley: Dag kiezen mislukt",
                f"Kon dag {args.datum} niet selecteren.")
            sys.exit(1)

        baan, geboekte_tijd = kies_baan_en_tijd(driver, args.tijd)
        if not baan:
            stuur_email(
                f"❌ ETV Volley: Geen baan beschikbaar op {args.datum}",
                f"Geen padelbaan beschikbaar op {args.datum} rondom {args.tijd}.\n"
                f"Reserveer zelf via etv-volley.nl/mijn")
            sys.exit(1)

        if not bevestig(driver):
            stuur_email("❌ ETV Volley: Bevestigen mislukt",
                f"Baan geselecteerd maar bevestigen mislukt op {args.datum}.")
            sys.exit(1)

    finally:
        driver.quit()

    datum_nl = datetime.strptime(args.datum, "%Y-%m-%d").strftime("%d-%m-%Y")
    tijdsverschil = f" (voorkeur was {args.tijd})" if geboekte_tijd != args.tijd else ""
    stuur_email(
        f"KNLTB GEBOEKT: {baan} – {datum_nl} om {geboekte_tijd}",
        f"✅ Padelbaan succesvol gereserveerd!\n\n"
        f"🎾 Baan:    {baan}\n"
        f"📅 Datum:   {datum_nl}\n"
        f"🕐 Tijd:    {geboekte_tijd} – 60 min{tijdsverschil}\n"
        f"👥 Spelers:\n"
        f"   1. {SPELER1}\n"
        f"   2. {args.speler2}\n"
        f"   3. {args.speler3}\n"
        f"   4. {args.speler4}\n\n"
        f"Zeg tegen Claude: '{baan} om {geboekte_tijd} is geboekt' om je agenda bij te werken."
    )
    log.info("✅ Klaar!")


if __name__ == "__main__":
    main()

"""
ETV Volley Padelbaan Auto-Reservering
Automatisch een padelbaan reserveren via etv-volley.nl/mijn
Na een succesvolle boeking wordt de afspraak direct in Google Agenda gezet.

Omgevingsvariabelen (GitHub Secrets):
  KNLTB_BONDSNUMMER              - Jouw bondsnummer / gebruikersnaam
  KNLTB_WACHTWOORD               - Jouw wachtwoord
  GOOGLE_CALENDAR_CREDENTIALS    - Inhoud van het service-account JSON-bestand
  GOOGLE_CALENDAR_ID             - Agenda-ID (bijv. 'primary' of je e-mailadres)
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime, timedelta

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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
LOGIN_URL    = "https://www.etv-volley.nl/mijn"
RESERVEER_URL = "https://www.etv-volley.nl/mijn/Reservations"

BONDSNUMMER  = os.environ.get("KNLTB_BONDSNUMMER", "")
WACHTWOORD   = os.environ.get("KNLTB_WACHTWOORD", "")
SPELER1      = "Joris van den Broek"

GOOGLE_CREDENTIALS = os.environ.get("GOOGLE_CALENDAR_CREDENTIALS", "")
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

PADEL_BANEN   = ["Padel 1", "Padel 2", "Padel 3", "Padel 4", "Padel 5", "Padel 6"]
WACHT_TIMEOUT = 15
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
    uur = int(tijd.split(":")[0])
    if uur < 12:  return "Ochtend"
    elif uur < 17: return "Middag"
    else:          return "Avond"


# ── Google Agenda ─────────────────────────────────────────────────────────────
def voeg_toe_aan_agenda(baan: str, datum: str, tijd: str, spelers: list):
    """Maak een afspraak aan in Google Agenda via Service Account."""
    if not GOOGLE_CREDENTIALS:
        log.warning("⚠️  GOOGLE_CALENDAR_CREDENTIALS niet ingesteld — agenda overgeslagen.")
        return

    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        creds_info = json.loads(GOOGLE_CREDENTIALS)
        creds = Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        start_dt = datetime.strptime(f"{datum} {tijd}", "%Y-%m-%d %H:%M")
        eind_dt  = start_dt + timedelta(hours=1)
        datum_nl = start_dt.strftime("%d-%m-%Y")

        event = {
            "summary": f"🎾 Padel – {baan} – ETV Volley",
            "location": "ETV Volley, Swaardvenstraat 10, 5048 AV Tilburg",
            "description": (
                f"Padelbaan automatisch gereserveerd.\n\n"
                f"Baan:    {baan}\n"
                f"Datum:   {datum_nl}\n"
                f"Tijd:    {tijd} – {eind_dt.strftime('%H:%M')}\n\n"
                f"Spelers:\n" +
                "\n".join(f"  {i+1}. {s}" for i, s in enumerate(spelers))
            ),
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Europe/Amsterdam",
            },
            "end": {
                "dateTime": eind_dt.isoformat(),
                "timeZone": "Europe/Amsterdam",
            },
            "colorId": "10",   # Groen (Sage) — passend bij padel
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 60},
                ],
            },
        }

        result = service.events().insert(
            calendarId=GOOGLE_CALENDAR_ID, body=event
        ).execute()
        log.info(f"✅ Google Agenda bijgewerkt: {result.get('htmlLink')}")

    except ImportError:
        log.error("❌ google-api-python-client niet geïnstalleerd.")
    except json.JSONDecodeError:
        log.error("❌ GOOGLE_CALENDAR_CREDENTIALS is geen geldig JSON-bestand.")
    except Exception as e:
        log.error(f"❌ Google Agenda bijwerken mislukt: {e}")


# ── Selenium driver ───────────────────────────────────────────────────────────
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


def maak_driver() -> uc.Chrome:
    opties = uc.ChromeOptions()
    opties.add_argument("--no-sandbox")
    opties.add_argument("--disable-dev-shm-usage")
    opties.add_argument("--disable-gpu")
    opties.add_argument("--window-size=1280,900")
    opties.add_argument("--lang=nl-NL")
    # Geen --headless: draait via Xvfb virtual display zodat Cloudflare ons niet detecteert
    versie = chrome_major_versie()
    driver = uc.Chrome(options=opties, version_main=versie)
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
def login(driver: uc.Chrome) -> bool:
    log.info(f"Navigeer naar {LOGIN_URL}")
    driver.get(LOGIN_URL)
    time.sleep(4)
    screenshot(driver, "01_login_pagina")

    # Accepteer cookie-banner (met expliciete wacht)
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

    # Log alle input-velden voor diagnose
    try:
        alle_inputs = driver.find_elements(By.TAG_NAME, "input")
        log.info(f"Gevonden input-velden ({len(alle_inputs)}):")
        for inp in alle_inputs:
            log.info(f"  type={inp.get_attribute('type')} name={inp.get_attribute('name')} "
                     f"id={inp.get_attribute('id')} placeholder={inp.get_attribute('placeholder')} "
                     f"visible={inp.is_displayed()}")
    except Exception as e:
        log.warning(f"Input-veld scan mislukt: {e}")

    try:
        gebruiker_veld = wacht_op(driver, By.XPATH,
            "//input[@type='text' or @type='email' "
            "or @name='username' or @name='Username' or @name='UserName' "
            "or @id='username' or @id='Username' or @id='UserName' "
            "or contains(@placeholder,'bondsnummer') or contains(@placeholder,'gebruikersnaam') "
            "or contains(@placeholder,'e-mail') or contains(@placeholder,'email')]")
        log.info(f"Gebruikersveld: name='{gebruiker_veld.get_attribute('name')}' "
                 f"id='{gebruiker_veld.get_attribute('id')}'")

        # Vul in via JS — triggert ook React/Vue native input events
        driver.execute_script("""
            var el = arguments[0], val = arguments[1];
            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, gebruiker_veld, BONDSNUMMER)
        log.info(f"Bondsnummer ingevuld via JS ({len(BONDSNUMMER)} tekens)")

        ww_veld = wacht_op(driver, By.XPATH, "//input[@type='password']")
        log.info(f"Wachtwoordveld: name='{ww_veld.get_attribute('name')}' "
                 f"id='{ww_veld.get_attribute('id')}'")

        driver.execute_script("""
            var el = arguments[0], val = arguments[1];
            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, ww_veld, WACHTWOORD)
        log.info(f"Wachtwoord ingevuld via JS ({len(WACHTWOORD)} tekens)")

        time.sleep(1)

        # Zoek de zichtbare submit-knop (niet de cookie-banner)
        submit_knop = None
        for sel in [
            "//button[@type='submit']",
            "//input[@type='submit']",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'inloggen')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]",
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'aanmelden')]",
        ]:
            try:
                for knop in driver.find_elements(By.XPATH, sel):
                    if knop.is_displayed():
                        log.info(f"Submit-knop gevonden: '{knop.text.strip()}' via {sel}")
                        submit_knop = knop
                        break
                if submit_knop:
                    break
            except Exception:
                pass

        if submit_knop:
            driver.execute_script("arguments[0].click();", submit_knop)
            log.info("Submit-knop geklikt via JS")
        else:
            log.warning("Geen submit-knop gevonden — gebruik Keys.RETURN als fallback")
            ww_veld.send_keys(Keys.RETURN)

        time.sleep(6)
        screenshot(driver, "02_na_login")
        log.info(f"URL na login: {driver.current_url}")

        # Log paginatekst voor foutmeldingen
        try:
            body_tekst = driver.find_element(By.TAG_NAME, "body").text
            for zoekterm in ["onjuist", "ongeldig", "fout", "incorrect", "error",
                             "geblokkeerd", "locked", "account", "blocked", "te veel"]:
                if zoekterm in body_tekst.lower():
                    log.warning(f"⚠️ '{zoekterm}' gevonden in paginatekst")
            log.info(f"Paginatitel na login: {driver.title}")
            log.info(f"Paginatekst (eerste 500): {body_tekst[:500]}")
        except Exception:
            pass

        # Controleer of wachtwoordveld nog zichtbaar is (= login mislukt)
        try:
            pw = driver.find_element(By.XPATH, "//input[@type='password']")
            if pw.is_displayed():
                log.error("❌ Inloggen mislukt — wachtwoordveld nog zichtbaar")
                screenshot(driver, "02b_login_mislukt")
                return False
        except Exception:
            pass  # Veld weg = inloggen gelukt

        log.info("✅ Ingelogd!")
        return True
    except TimeoutException as e:
        log.error(f"❌ Inloggen mislukt: {e}")
        screenshot(driver, "login_fout")
        return False


# ── STAP 2: Baan afhangen klikken ────────────────────────────────────────────
def klik_baan_afhangen(driver: uc.Chrome) -> bool:
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
def voeg_spelers_toe(driver: uc.Chrome, speler2: str, speler3: str, speler4: str) -> bool:
    log.info("Spelers toevoegen...")
    time.sleep(2)
    screenshot(driver, "05_spelers_pagina")

    for speler in [speler2, speler3, speler4]:
        log.info(f"Speler toevoegen: {speler}")
        try:
            zoek_veld = wacht_op(driver, By.XPATH,
                "//input[contains(@placeholder,'zoek') or contains(@placeholder,'naam') "
                "or contains(@placeholder,'speler') or contains(@class,'search')]")
            zoek_veld.clear()
            zoek_veld.send_keys(speler.split()[0])
            time.sleep(2)

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
def kies_dag(driver: uc.Chrome, datum: str, tijd: str) -> bool:
    log.info(f"Dag kiezen: {datum}, dagdeel: {dagdeel(tijd)}")
    time.sleep(2)
    screenshot(driver, "07_dag_pagina")

    doel_datum = datetime.strptime(datum, "%Y-%m-%d")
    dag_nr     = str(doel_datum.day)
    gewenst_dagdeel = dagdeel(tijd)

    try:
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
def kies_baan_en_tijd(driver: uc.Chrome, voorkeur_tijd: str) -> tuple:
    log.info("Baankeuze pagina...")
    time.sleep(2)
    screenshot(driver, "09_baan_pagina")

    tijden = genereer_tijden(voorkeur_tijd)
    log.info(f"Tijden om te proberen: {tijden}")

    for tijd in tijden:
        for baan in PADEL_BANEN:
            log.info(f"Probeer {baan} om {tijd}...")
            try:
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
                screenshot(driver, "10_baan_geselecteerd")
                return baan, tijd
            except NoSuchElementException:
                continue

    log.error("❌ Geen beschikbare padelbaan/tijd gevonden!")
    screenshot(driver, "baan_fout")
    return "", ""


# ── STAP 6: Bevestigen ────────────────────────────────────────────────────────
def bevestig(driver: uc.Chrome) -> bool:
    log.info("Bevestigen...")
    try:
        volgende = wacht_op(driver, By.XPATH,
            "//button[contains(text(),'Volgende') or contains(text(),'Next')] "
            "| //a[contains(text(),'Volgende')]")
        volgende.click()
        time.sleep(2)
        screenshot(driver, "11_bevestig_pagina")

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


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
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
            log.error("🚫 Inloggen mislukt — controleer KNLTB_BONDSNUMMER en KNLTB_WACHTWOORD")
            sys.exit(1)

        if not klik_baan_afhangen(driver):
            log.error("🚫 'Baan afhangen' knop niet gevonden")
            sys.exit(1)

        if not voeg_spelers_toe(driver, args.speler2, args.speler3, args.speler4):
            log.error("🚫 Speler niet gevonden — controleer spelernamen")
            sys.exit(1)

        if not kies_dag(driver, args.datum, args.tijd):
            log.error(f"🚫 Dag {args.datum} kon niet worden geselecteerd")
            sys.exit(1)

        baan, geboekte_tijd = kies_baan_en_tijd(driver, args.tijd)
        if not baan:
            log.error(f"🚫 Geen padelbaan beschikbaar op {args.datum} rondom {args.tijd}")
            sys.exit(1)

        if not bevestig(driver):
            log.error("🚫 Bevestigen mislukt")
            sys.exit(1)

    finally:
        driver.quit()

    # ── Succes: Google Agenda bijwerken ───────────────────────────────────────
    spelers = [SPELER1, args.speler2, args.speler3, args.speler4]
    datum_nl = speeldatum.strftime("%d-%m-%Y")
    tijdsverschil = f" (voorkeur was {args.tijd})" if geboekte_tijd != args.tijd else ""

    log.info("=" * 50)
    log.info(f"✅ GEBOEKT: {baan} op {datum_nl} om {geboekte_tijd}{tijdsverschil}")
    log.info(f"   Spelers: {', '.join(spelers)}")
    log.info("=" * 50)

    voeg_toe_aan_agenda(baan, args.datum, geboekte_tijd, spelers)


if __name__ == "__main__":
    main()

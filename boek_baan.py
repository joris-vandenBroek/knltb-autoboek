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


# ── Navigatie-hulpfunctie ─────────────────────────────────────────────────────

def _zoek_knop(driver: uc.Chrome, labels: list) -> object:
    """
    Zoek een zichtbare knop/link die een van de gegeven labels bevat.
    Gebruikt contains(.,label) zodat child-elementen (zoals pijl-iconen) geen probleem zijn.
    """
    for label in labels:
        for sel in [
            f"//button[contains(.,'{label}')]",
            f"//a[contains(.,'{label}')]",
            f"//*[@role='button'][contains(.,'{label}')]",
        ]:
            try:
                for el in driver.find_elements(By.XPATH, sel):
                    if el.is_displayed():
                        log.info(f"Knop '{label}' gevonden: '{el.text.strip()[:40]}'")
                        return el
            except Exception:
                pass
    return None


# ── STAP 3: Spelers toevoegen ─────────────────────────────────────────────────

def _zoek_veld_spelers(driver: uc.Chrome):
    """Geef het eerste zichtbare text/search-input terug op de spelerspagina."""
    alle = driver.find_elements(By.XPATH, "//input[@type='text' or @type='search']")
    for inp in alle:
        if inp.is_displayed() and inp.is_enabled():
            log.info(f"  Zoekveld: placeholder='{inp.get_attribute('placeholder')}' "
                     f"id='{inp.get_attribute('id')}'")
            return inp
    return None


def _voeg_speler_toe(driver: uc.Chrome, speler: str, index: int) -> bool:
    """Zoek en selecteer één speler; probeer ook 'Recent mee gespeeld'-kaartjes."""
    achternaam = speler.split()[-1]

    # 1. Probeer eerst via 'Recent mee gespeeld' – klik op het +-knopje
    try:
        recent_plus = driver.find_elements(By.XPATH,
            f"//div[contains(@class,'recent') or contains(@class,'Recent')]"
            f"//*[contains(.,'{achternaam}')]"
            f"/ancestor::*[contains(@class,'player') or contains(@class,'card') or contains(@class,'item')]"
            f"//*[contains(@class,'add') or contains(@class,'plus') or text()='+']")
        for knop in recent_plus:
            if knop.is_displayed():
                driver.execute_script("arguments[0].click();", knop)
                log.info(f"  ✅ {speler} via 'Recent mee gespeeld' toegevoegd")
                time.sleep(1)
                return True
    except Exception:
        pass

    # 2. Zoek via het zoekveld
    zoek_veld = _zoek_veld_spelers(driver)
    if not zoek_veld:
        log.error(f"  ❌ Zoekveld niet gevonden voor '{speler}'")
        return False

    # 2b. Typ de naam via send_keys (simuleert echte toetsaanslagen, triggert typeahead)
    #     Probeer meerdere zoektermen tot er een suggestie verschijnt
    woorden     = speler.split()
    # Probeer: volledige naam → achternaam → voornaam+achternaam (zonder tussenvoegsel)
    zoektermen  = [speler, achternaam]
    if len(woorden) >= 3:
        zoektermen.insert(1, woorden[0] + " " + woorden[-1])   # "Chris Waardenburg"

    geselecteerd = False
    for zoekterm in zoektermen:
        # Wis het veld en typ de zoekterm karakter voor karakter
        zoek_veld.click()
        zoek_veld.send_keys(Keys.CONTROL + "a")
        zoek_veld.send_keys(Keys.DELETE)
        time.sleep(0.3)
        zoek_veld.send_keys(zoekterm)
        log.info(f"  Zoekterm ingevuld: '{zoekterm}'")
        screenshot(driver, f"05b_zoek_{index}_{achternaam}")

        # Wacht tot er een suggestie met de achternaam verschijnt (max 8s)
        try:
            WebDriverWait(driver, 8).until(
                lambda d: any(
                    el.is_displayed() and achternaam.lower() in el.text.lower()
                    for el in d.find_elements(By.XPATH,
                        f"//*[contains(.,'{achternaam}') and not(self::input)"
                        f"    and not(self::html) and not(self::body)]")
                )
            )
        except TimeoutException:
            log.info(f"  Geen suggestie na 8s voor zoekterm '{zoekterm}', volgende proberen...")
            continue

        # 3. Klik de suggestie — zoek het kleinste zichtbare element met de achternaam
        selectors = [
            f"//*[@role='option'][contains(.,'{achternaam}')]",
            f"//li[contains(.,'{achternaam}')]",
            f"//div[contains(@class,'player') or contains(@class,'suggestion')"
            f"      or contains(@class,'result') or contains(@class,'item')]"
            f"[contains(.,'{achternaam}')]",
            f"//*[contains(.,'{achternaam}') and not(self::html) and not(self::body)"
            f"    and not(self::div[@id]) and not(self::input)]",
        ]
        for sel in selectors:
            try:
                for el in driver.find_elements(By.XPATH, sel):
                    tekst = el.text.strip()
                    if el.is_displayed() and achternaam.lower() in tekst.lower():
                        log.info(f"  Suggestie via '{sel[:60]}': '{tekst[:60]}'")
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(1.2)
                        log.info(f"  ✅ {speler} geselecteerd via zoekterm '{zoekterm}'")
                        geselecteerd = True
                        break
            except Exception as e:
                log.debug(f"  Selector overgeslagen: {e}")
            if geselecteerd:
                break
        if geselecteerd:
            return True

    # Geen enkele zoekterm leverde resultaat op
    log.error(f"  ❌ Geen suggestie voor '{speler}' (geprobeerd: {zoektermen})")
    try:
        zichtbaar_tekst = driver.find_element(By.TAG_NAME, "body").text
        log.error(f"  Paginatekst (500 tekens): {zichtbaar_tekst[:500]}")
    except Exception:
        pass
    screenshot(driver, f"05c_niet_gevonden_{achternaam}")
    return False


def voeg_spelers_toe(driver: uc.Chrome, speler2: str, speler3: str, speler4: str) -> bool:
    log.info("Spelers toevoegen...")
    time.sleep(2)
    screenshot(driver, "05_spelers_pagina")

    for i, speler in enumerate([speler2, speler3, speler4], start=2):
        log.info(f"Speler {i} toevoegen: '{speler}'")
        if not _voeg_speler_toe(driver, speler, i):
            return False

    screenshot(driver, "06_spelers_toegevoegd")

    volgende = _zoek_knop(driver, ["Volgende", "Next"])
    if volgende:
        driver.execute_script("arguments[0].click();", volgende)
        time.sleep(2)
        log.info("✅ Spelers toegevoegd, naar dagkeuze")
        return True
    log.error("❌ 'Volgende' knop niet gevonden na spelers")
    try:
        log.error(f"Paginatekst: {driver.find_element(By.TAG_NAME,'body').text[:400]}")
    except Exception:
        pass
    screenshot(driver, "volgende_fout_spelers")
    return False


# ── STAP 4: Dag en dagdeel kiezen ────────────────────────────────────────────
def kies_dag(driver: uc.Chrome, datum: str, tijd: str) -> bool:
    log.info(f"Dag kiezen: {datum}, dagdeel: {dagdeel(tijd)}")
    time.sleep(2)
    screenshot(driver, "07_dag_pagina")

    doel_datum      = datetime.strptime(datum, "%Y-%m-%d")
    dag_nr          = str(doel_datum.day)
    gewenst_dagdeel = dagdeel(tijd)
    log.info(f"Zoek dag={dag_nr}, dagdeel='{gewenst_dagdeel}'")

    # Navigeer naar de juiste week als de dag niet zichtbaar is
    for _ in range(8):
        if dag_nr in driver.find_element(By.TAG_NAME, "body").text:
            break
        volgende_week = _zoek_knop(driver, [">"])
        if volgende_week:
            driver.execute_script("arguments[0].click();", volgende_week)
            time.sleep(1.5)
        else:
            break

    # Stap A: klik de dag-header om de Bootstrap-accordion open te klappen.
    # (elementFromPoint pikt anders de collapse-wrapper op, niet de cel zelf.)
    dag_klik = driver.execute_script("""
        var dagNr = arguments[0];
        var alle  = Array.from(document.querySelectorAll('*'));
        var dagEls = alle.filter(function(el) {
            if (!el.offsetParent) return false;
            var tokens = (el.innerText || '').trim().split(/\s+/);
            return tokens.indexOf(dagNr) >= 0 && el.children.length <= 1;
        });
        if (!dagEls.length) return 'GEEN_DAG: ' + dagNr;
        var r = dagEls[0].getBoundingClientRect();
        dagEls[0].click();
        return 'DAG_GEKLIKT x=' + Math.round(r.left + r.width / 2);
    """, dag_nr)
    log.info(f"Dag accordion klik: {dag_klik}")
    time.sleep(0.7)

    # Stap B: vind alle zichtbare dagdeel-cellen en klik de cel wiens
    # X-middelpunt het dichtst bij het X-middelpunt van de dag-header ligt.
    resultaat = driver.execute_script("""
        var dagNr   = arguments[0];
        var dagdeel = arguments[1];
        var alle = Array.from(document.querySelectorAll('*'));

        var dagEls = alle.filter(function(el) {
            if (!el.offsetParent) return false;
            var tokens = (el.innerText || '').trim().split(/\s+/);
            return tokens.indexOf(dagNr) >= 0 && el.children.length <= 1;
        });
        if (!dagEls.length) return 'NIET_GEVONDEN: geen dag-element voor ' + dagNr;

        var dagdeelEls = alle.filter(function(el) {
            if (!el.offsetParent) return false;
            var txt = (el.innerText || '').trim();
            return txt === dagdeel && el.children.length === 0;
        });
        if (!dagdeelEls.length) return 'NIET_GEVONDEN: geen dagdeel-element voor ' + dagdeel;

        var dagR = dagEls[0].getBoundingClientRect();
        var dagX = dagR.left + dagR.width / 2;

        dagdeelEls.sort(function(a, b) {
            var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
            return Math.abs((ra.left + ra.width / 2) - dagX)
                 - Math.abs((rb.left + rb.width / 2) - dagX);
        });

        var target = dagdeelEls[0];
        var tr = target.getBoundingClientRect();
        target.click();
        return 'OK dag=' + dagNr + ' dagdeel=' + dagdeel
             + ' target_x=' + Math.round(tr.left + tr.width / 2)
             + ' dag_x='    + Math.round(dagX);
    """, dag_nr, gewenst_dagdeel)

    log.info(f"JS dag-selectie: {resultaat}")

    if resultaat and resultaat.startswith("OK"):
        log.info(f"✅ Dag {dag_nr} + dagdeel '{gewenst_dagdeel}' geselecteerd")
        time.sleep(1)
    else:
        # Fallback: klik de eerste zichtbare niet-disabled dagdeel-cel
        log.warning(f"JS mislukt ({resultaat}), probeer fallback...")
        try:
            for el in driver.find_elements(By.XPATH,
                    f"//*[normalize-space(.)='{gewenst_dagdeel}']"):
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    log.info(f"Fallback: eerste zichtbare '{gewenst_dagdeel}' geklikt")
                    time.sleep(1)
                    break
        except Exception as e:
            log.error(f"❌ Dagdeel-fallback mislukt: {e}")
            screenshot(driver, "dag_fout")
            return False

    screenshot(driver, "08_dag_geselecteerd")
    volgende = _zoek_knop(driver, ["Volgende", "Next"])
    if volgende:
        driver.execute_script("arguments[0].click();", volgende)
        time.sleep(2)
        log.info("✅ Naar baankeuze")
        return True
    log.error("❌ 'Volgende' knop niet gevonden na dag")
    screenshot(driver, "volgende_fout_dag")
    return False


# ── STAP 5: Baan en tijd kiezen ──────────────────────────────────────────────
def kies_baan_en_tijd(driver: uc.Chrome, voorkeur_tijd: str) -> tuple:
    log.info("Baankeuze pagina laden...")

    # Wacht tot de tijdslot-pagina geladen is: er verschijnen elementen zoals
    # "08:00", "09:30" etc. Padelbaan-namen staan pas zichtbaar NADAT een
    # tijdslot geselecteerd is, dus die zijn geen bruikbaar laadsignaal.
    try:
        WebDriverWait(driver, 20).until(
            lambda d: ":00" in d.find_element(By.TAG_NAME, "body").text
                      or ":30" in d.find_element(By.TAG_NAME, "body").text
        )
        log.info("✅ Tijdslot-pagina geladen (tijden zichtbaar)")
    except TimeoutException:
        log.warning("⚠️ Tijdslot-pagina niet geladen na 20s — toch proberen")

    time.sleep(1)
    screenshot(driver, "09_baan_pagina")

    tijden = genereer_tijden(voorkeur_tijd)
    log.info(f"Tijden om te proberen: {tijden}")

    # Log paginatekst voor diagnose (eerste 3000 tekens)
    try:
        pagina = driver.find_element(By.TAG_NAME, "body").text
        log.info(f"Baan-pagina tekst (3000): {pagina[:3000]}")
    except Exception:
        pass

    # Baankeuze = tijdslot klikken. Het systeem koppelt daarna een baan.
    # Klik het eerste beschikbare tijdslot dat overeenkomt met gewenste tijd.
    for tijd in tijden:
        log.info(f"Zoek tijdslot '{tijd}'...")

        resultaat = driver.execute_script("""
            var tijd = arguments[0];
            var alle = Array.from(document.querySelectorAll('*'));

            for (var el of alle) {
                if (!el.offsetParent) continue;  // niet zichtbaar
                var txt = (el.innerText || '').trim();

                // Exacte match of "15:00 - 16:00" / "15:00 tot 16:00" / "15:00[newline]..."
                if (txt !== tijd &&
                    !txt.startsWith(tijd + ' ') &&
                    !txt.startsWith(tijd + '-') &&
                    txt.split(/\s/)[0] !== tijd) continue;

                // Geen disabled-vinkje
                if (el.classList.contains('disabled') ||
                    el.hasAttribute('disabled') ||
                    el.getAttribute('aria-disabled') === 'true') continue;

                el.click();
                return 'OK tijd=' + tijd + ' tag=' + el.tagName +
                       ' class=' + (el.className || '');
            }
            return 'NIET_GEVONDEN tijd=' + tijd;
        """, tijd)

        log.info(f"  JS: {resultaat}")
        if resultaat and resultaat.startswith("OK"):
            time.sleep(2)
            screenshot(driver, "10_baan_geselecteerd")

            # Bepaal welke baan geselecteerd is vanuit de paginatekst
            baan = ""
            try:
                tekst = driver.find_element(By.TAG_NAME, "body").text
                for b in PADEL_BANEN:
                    if b in tekst:
                        baan = b
                        break
            except Exception:
                pass

            log.info(f"✅ Tijdslot {tijd} geselecteerd, baan={baan or '(onbekend)'}")
            return baan, tijd

    log.error("❌ Geen beschikbaar tijdslot gevonden!")
    screenshot(driver, "baan_fout")
    return "", ""


# ── STAP 6: Bevestigen ────────────────────────────────────────────────────────
def bevestig(driver: uc.Chrome) -> bool:
    log.info("Bevestigen...")
    try:
        volgende = _zoek_knop(driver, ["Volgende", "Next"])
        if volgende:
            driver.execute_script("arguments[0].click();", volgende)
            time.sleep(2)
            screenshot(driver, "11_bevestig_pagina")

        bevestig_knop = _zoek_knop(driver, ["Bevestig", "Confirm", "Boek", "Reserveer"])
        if not bevestig_knop:
            log.error("❌ Bevestig-knop niet gevonden")
            try:
                log.error(f"Paginatekst: {driver.find_element(By.TAG_NAME,'body').text[:400]}")
            except Exception:
                pass
            screenshot(driver, "bevestig_fout")
            return False
        driver.execute_script("arguments[0].click();", bevestig_knop)
        time.sleep(3)
        screenshot(driver, "12_na_bevestiging")
        log.info("✅ Bevestigd!")
        return True
    except Exception as e:
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

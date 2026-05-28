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
from selenium.webdriver.common.action_chains import ActionChains
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
    """
    Zoek en selecteer één speler.
    BELANGRIJK: gebruik ActionChains voor alle klikken — JS execute_script().click()
    genereert events met isTrusted=false die de site's jQuery handlers negeren,
    waardoor de speler niet in de server-sessie wordt opgeslagen.
    """
    achternaam = speler.split()[-1]

    def _action_klik(el):
        """Klik via ActionChains (isTrusted=true) met JS-click als fallback."""
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.2)
            ActionChains(driver).move_to_element(el).click().perform()
            return True
        except Exception as e:
            log.warning(f"  ActionChains klik mislukt ({e}), probeer JS click")
            try:
                driver.execute_script("arguments[0].click();", el)
                return True
            except Exception:
                return False

    # 1. Probeer eerst via 'Recent mee gespeeld' – klik op het +-knopje via ActionChains
    try:
        driver.implicitly_wait(0)
        recent_plus = driver.find_elements(By.XPATH,
            f"//div[contains(@class,'recent') or contains(@class,'Recent')]"
            f"//*[contains(.,'{achternaam}')]"
            f"/ancestor::*[contains(@class,'player') or contains(@class,'card') or contains(@class,'item')]"
            f"//*[contains(@class,'add') or contains(@class,'plus') or text()='+']")
        driver.implicitly_wait(5)
        for knop in recent_plus:
            if knop.is_displayed():
                if _action_klik(knop):
                    log.info(f"  ✅ {speler} via 'Recent mee gespeeld' toegevoegd (ActionChains)")
                    time.sleep(1.5)
                    return True
    except Exception:
        driver.implicitly_wait(5)

    # 2. Zoek via het zoekveld
    zoek_veld = _zoek_veld_spelers(driver)
    if not zoek_veld:
        log.error(f"  ❌ Zoekveld niet gevonden voor '{speler}'")
        return False

    woorden    = speler.split()
    zoektermen = [speler, achternaam]
    if len(woorden) >= 3:
        zoektermen.insert(1, woorden[0] + " " + woorden[-1])  # "Chris Waardenburg"

    geselecteerd = False
    for zoekterm in zoektermen:
        # Wis het veld en typ de zoekterm (echte toetsaanslagen → typeahead)
        zoek_veld.click()
        zoek_veld.send_keys(Keys.CONTROL + "a")
        zoek_veld.send_keys(Keys.DELETE)
        time.sleep(0.3)
        zoek_veld.send_keys(zoekterm)
        log.info(f"  Zoekterm ingevuld: '{zoekterm}'")
        screenshot(driver, f"05b_zoek_{index}_{achternaam}")

        # Wacht tot suggestie verschijnt (max 8s)
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
            log.info(f"  Geen suggestie na 8s voor '{zoekterm}', volgende proberen...")
            continue

        # 3. Kies het KLEINSTE zichtbare element dat de achternaam bevat.
        #    Groot element (bijv. sectiecontainer 'Spelers') overslaan.
        selectors = [
            f"//*[@role='option'][contains(.,'{achternaam}')]",
            f"//li[contains(.,'{achternaam}')]",
            f"//div[contains(@class,'player') or contains(@class,'suggestion')"
            f"      or contains(@class,'result') or contains(@class,'item')]"
            f"[contains(.,'{achternaam}')]",
            f"//*[contains(.,'{achternaam}') and not(self::html) and not(self::body)"
            f"    and not(self::div[@id]) and not(self::input)]",
        ]
        kandidaten = []
        driver.implicitly_wait(0)
        for sel in selectors:
            try:
                for el in driver.find_elements(By.XPATH, sel):
                    tekst = el.text.strip()
                    if el.is_displayed() and achternaam.lower() in tekst.lower() \
                            and 0 < len(tekst) < 200:
                        kandidaten.append((len(tekst), el, tekst, sel))
            except Exception:
                pass
        driver.implicitly_wait(5)

        if kandidaten:
            # Sorteer op tekstlengte en klik de kleinste
            kandidaten.sort(key=lambda x: x[0])
            _, best_el, best_tekst, best_sel = kandidaten[0]
            log.info(f"  Suggestie (kleinste, {len(best_tekst)} tekens): "
                     f"'{best_tekst[:60]}' via '{best_sel[:50]}'")
            if _action_klik(best_el):
                time.sleep(1.5)
                log.info(f"  ✅ {speler} geselecteerd via ActionChains (zoekterm '{zoekterm}')")
                geselecteerd = True

        if geselecteerd:
            return True

    # Geen suggestie gevonden
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
        # Gebruik _submit_knop (requestSubmit chain) zodat speler-IDs als form-data
        # naar de server worden gestuurd. Losse JS .click() negeert form submission.
        methode = _submit_knop(driver, volgende)
        log.info(f"  Volgende (spelers) methode: {methode}")
        # Wacht op URL-verandering (max 8s)
        url_voor = driver.current_url
        try:
            WebDriverWait(driver, 8).until(lambda d: d.current_url != url_voor)
        except TimeoutException:
            pass
        time.sleep(1)
        log.info(f"✅ Spelers toegevoegd, URL: {driver.current_url}")
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
    _sluit_cookie_banner(driver)
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

    # Log alle div[data-date] elementen voor diagnose
    alle_dayparts = driver.execute_script("""
        return Array.from(document.querySelectorAll('[data-date]')).map(function(el) {
            return el.getAttribute('data-date') + ':' + (el.innerText || '').trim().slice(0, 20);
        }).join(' | ');
    """)
    log.info(f"Alle data-date elementen: {alle_dayparts}")

    # Stap A+B gecombineerd: zoek het div.daypart voor de juiste datum+dagdeel
    # direct via data-date attribuut (bypass accordeon-toggle issues).
    # De datum in de ISO string begint met het doeldatum (YYYY-MM-DD).
    daypart_el = driver.execute_script("""
        var targetDate = arguments[0];   // bijv. "2026-05-28"
        var dagdeel    = arguments[1];   // bijv. "Middag"

        // Zoek alle [data-date] elementen waarvan data-date met de doeldatum begint
        var candidates = Array.from(document.querySelectorAll('[data-date]'))
            .filter(function(el) {
                var dd = el.getAttribute('data-date') || '';
                return dd.startsWith(targetDate);
            });
        if (!candidates.length) return null;

        // Kies het element met de dagdeel-tekst
        for (var i = 0; i < candidates.length; i++) {
            var txt = (candidates[i].innerText || '').trim();
            if (txt === dagdeel || txt.includes(dagdeel)) return candidates[i];
        }
        // Geen tekst-match: neem het eerste beschikbare datumcandidate
        return candidates[0];
    """, datum, gewenst_dagdeel)

    if not daypart_el:
        log.error(f"❌ div.daypart voor {datum} / {gewenst_dagdeel} niet gevonden")
        screenshot(driver, "dag_fout")
        return False

    data_date = driver.execute_script("return arguments[0].getAttribute('data-date');", daypart_el)
    log.info(f"Gevonden daypart: data-date={data_date}")

    # Klik het div.daypart element via een dispatched MouseEvent DIRECT op het element.
    # Dit triggert de click-handler op het element zelf (geen bubbling vanuit kind).
    driver.execute_script("""
        var el = arguments[0];
        el.scrollIntoView({block: 'center'});
        var rect = el.getBoundingClientRect();
        var cx = rect.left + rect.width / 2;
        var cy = rect.top + rect.height / 2;
        ['mouseover', 'mouseenter', 'mousemove',
         'mousedown', 'mouseup', 'click'].forEach(function(type) {
            el.dispatchEvent(new MouseEvent(type, {
                bubbles: true, cancelable: true, view: window,
                clientX: cx, clientY: cy
            }));
        });
    """, daypart_el)
    log.info(f"Daypart geklikt via dispatchEvent")
    time.sleep(2)  # wacht op eventuele AJAX-respons

    # Zet ALTIJD ook de hidden selectedDate input direct (backup)
    set_ok = driver.execute_script("""
        var input = document.querySelector('input[name="selectedDate"]');
        if (!input) return false;
        var setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        setter.call(input, arguments[0]);
        input.dispatchEvent(new Event('input',  {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
        return input.value;
    """, data_date)
    log.info(f"selectedDate gezet: {set_ok}")

    log.info(f"✅ Dag {dag_nr} + dagdeel '{gewenst_dagdeel}' geselecteerd")
    screenshot(driver, "08_dag_geselecteerd")

    # Zoek de stap-nav Volgende (type=submit, class='next', rechtsonder de tabel)
    volgende = driver.execute_script("""
        var alle = Array.from(document.querySelectorAll('button, a, [role="button"]'))
            .filter(function(el) {
                return el.offsetParent && (el.innerText || '').trim() === 'Volgende';
            });
        if (!alle.length) return null;
        var el, cls;
        for (var i = 0; i < alle.length; i++) {
            el = alle[i]; cls = (el.className || '').toLowerCase();
            if ((el.getAttribute('type') || '') === 'submit' && cls.includes('next')) return el;
        }
        for (var i = 0; i < alle.length; i++) {
            el = alle[i];
            if ((el.getAttribute('type') || '') === 'submit') return el;
        }
        return alle[alle.length - 1];
    """)
    log.info(f"Volgende knop: {bool(volgende)}")

    if not volgende:
        log.error("❌ Geen 'Volgende' knop gevonden na dag")
        screenshot(driver, "volgende_fout_dag")
        return False

    # Submit via requestSubmit (HTML-spec-conform: triggert validatie + pagina-transitie)
    methode = driver.execute_script("""
        var btn  = arguments[0];
        var form = btn.closest('form');
        if (form && form.requestSubmit) {
            try { form.requestSubmit(btn); return 'requestSubmit'; }
            catch(e) { }
        }
        if (form) { form.submit(); return 'form.submit'; }
        btn.click(); return 'btn.click';
    """, volgende)
    log.info(f"Volgende submit methode: {methode}")

    # Wacht op navigatie naar ReservationsCourt (max 12s)
    try:
        WebDriverWait(driver, 12).until(
            lambda d: "ReservationsCourt" in d.current_url
        )
        log.info(f"✅ Naar baankeuze: {driver.current_url}")
        return True
    except TimeoutException:
        pass

    # Geen URL-change: controleer of tijdsloten al zichtbaar zijn (AJAX-wizard)
    url_na = driver.current_url
    log.info(f"URL na requestSubmit: {url_na}")
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
        log.info(f"Body na requestSubmit (500): {body[:500]}")
        if ":00" in body or ":30" in body:
            log.info("✅ Tijdsloten zichtbaar — naar baankeuze (AJAX wizard)")
            return True
    except Exception:
        pass

    # requestSubmit navigeerde niet — probeer ActionChains als fallback
    log.warning("requestSubmit werkte niet — probeer ActionChains click op Volgende")
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", volgende)
        time.sleep(0.3)
        ActionChains(driver).move_to_element(volgende).click().perform()
        log.info("ActionChains Volgende geklikt")
    except Exception as e:
        log.warning(f"ActionChains mislukt ({e}), JS click als laatste redmiddel")
        driver.execute_script("arguments[0].click();", volgende)

    # Wacht nogmaals op ReservationsCourt of tijdsloten
    try:
        WebDriverWait(driver, 15).until(
            lambda d: "ReservationsCourt" in d.current_url
                      or ":00" in d.find_element(By.TAG_NAME, "body").text
                      or ":30" in d.find_element(By.TAG_NAME, "body").text
        )
        log.info(f"✅ Naar baankeuze na ActionChains: {driver.current_url}")
        return True
    except TimeoutException:
        try:
            body = driver.find_element(By.TAG_NAME, "body").text
            log.error(f"❌ Geen baankeuze na ActionChains — URL: {driver.current_url} | body: {body[:300]}")
        except Exception:
            pass
        screenshot(driver, "volgende_fout_dag")
        return False


# ── STAP 5: Baan en tijd kiezen ──────────────────────────────────────────────
def _sluit_cookie_banner(driver: uc.Chrome):
    """
    Sluit de cookie-banner als die zichtbaar is.
    Zet implicit_wait tijdelijk op 0 zodat find_elements() direct terugkeert als er
    geen banner is — anders wacht Selenium 5s per XPATH = 25s totaal voor niets.
    """
    driver.implicitly_wait(0)
    try:
        for xpath in [
            "//button[contains(normalize-space(),'Accepteer')]",
            "//button[contains(normalize-space(),'Accept')]",
            "//button[contains(normalize-space(),'Weiger')]",
            "//button[contains(normalize-space(),'Sluiten')]",
            "//a[contains(normalize-space(),'Accepteer')]",
        ]:
            try:
                els = driver.find_elements(By.XPATH, xpath)
                for el in els:
                    if el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        log.info(f"🍪 Cookie-banner gesloten via '{el.text.strip()[:30]}'")
                        time.sleep(0.8)
                        return
            except Exception:
                pass
    finally:
        driver.implicitly_wait(5)


def kies_baan_en_tijd(driver: uc.Chrome, voorkeur_tijd: str) -> tuple:
    log.info("Baankeuze pagina laden...")

    # Wacht tot de tijdslot-pagina geladen is
    try:
        WebDriverWait(driver, 30).until(
            lambda d: ":00" in d.find_element(By.TAG_NAME, "body").text
                      or ":30" in d.find_element(By.TAG_NAME, "body").text
        )
        log.info("✅ Tijdslot-pagina geladen (tijden zichtbaar)")
    except TimeoutException:
        try:
            log.warning(f"⚠️ Tijdslot-pagina niet geladen na 30s — bodytekst: "
                        f"{driver.find_element(By.TAG_NAME,'body').text[:500]}")
        except Exception:
            log.warning("⚠️ Tijdslot-pagina niet geladen na 30s — body niet leesbaar")

    time.sleep(1)

    # ── Sluit cookie-banner vóór we iets klikken ─────────────────────────────
    _sluit_cookie_banner(driver)

    screenshot(driver, "09_baan_pagina")

    tijden = genereer_tijden(voorkeur_tijd)
    log.info(f"Tijden om te proberen: {tijden}")

    # Log paginatekst voor diagnose
    try:
        pagina = driver.find_element(By.TAG_NAME, "body").text
        log.info(f"Baan-pagina tekst (3000): {pagina[:3000]}")
    except Exception:
        pass

    # ── Scroll naar padel-rijen zodat getBoundingClientRect() klopt ──────────
    # Padel-banen staan onderaan het grid; scroll ze eerst in beeld zodat de
    # browser hun layout berekend heeft en de Y-coördinaten kloppen.
    try:
        scroll_result = driver.execute_script("""
            var padelNamen = arguments[0];
            var allEls = Array.from(document.querySelectorAll('*'));
            for (var i = 0; i < allEls.length; i++) {
                var el  = allEls[i];
                var txt = (el.innerText || '').trim();
                if (txt.length === 0 || txt.length > 25) continue;
                for (var n = 0; n < padelNamen.length; n++) {
                    if (txt.indexOf(padelNamen[n]) >= 0) {
                        el.scrollIntoView({block: 'center', behavior: 'instant'});
                        return 'Gevonden en gescrolled: ' + txt;
                    }
                }
            }
            // Fallback: scroll naar 70% van paginahoogte
            window.scrollTo(0, document.body.scrollHeight * 0.7);
            return 'Fallback scroll 70%';
        """, PADEL_BANEN)
        log.info(f"Scroll naar padel: {scroll_result}")
        time.sleep(0.8)
        _sluit_cookie_banner(driver)
    except Exception as e:
        log.warning(f"Scroll naar padel mislukt: {e}")

    for tijd in tijden:
        log.info(f"Zoek padel tijdslot '{tijd}'...")

        # Zoek tijdslot in een padel-rij via ABSOLUTE document-Y (scroll-onafhankelijk).
        # getBoundingClientRect().top + window.scrollY = absolute document-Y.
        # Strategie:
        #   1. Vind padel-label elementen (kleine tekst ≤25 tekens met "Padel N")
        #      en bereken hun absolute document-Y.
        #   2. Verzamel alle .timeincourt / [data-hour] cellen met de gewenste tijd
        #      en bereken hun absolute document-Y.
        #   3. Kies de tijdcel met de kleinste absolute Y-afstand tot een padel-label.
        #   4. Geen match binnen 120px → return null (weiger smashcourt als fallback).
        result = driver.execute_script("""
            var tijd       = arguments[0];
            var padelNamen = arguments[1];

            // ── Stap 1: padel-labels → absolute document-Y ────────────────────────
            var padelItems = [];
            document.querySelectorAll('*').forEach(function(el) {
                var r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) return;   // niet gerenderd/zichtbaar
                var txt = (el.innerText || '').trim();
                if (txt.length === 0 || txt.length > 25) return;  // te lang = container
                for (var n = 0; n < padelNamen.length; n++) {
                    if (txt.indexOf(padelNamen[n]) >= 0) {
                        padelItems.push({
                            name: padelNamen[n],
                            absY: r.top + window.scrollY + r.height / 2
                        });
                        break;
                    }
                }
            });

            window._padelCount = padelItems.length;
            window._padelAbsY  = padelItems.map(function(p) { return Math.round(p.absY); });

            // ── Stap 2: tijdcellen → absolute document-Y ─────────────────────────
            var tijdItems = Array.from(
                document.querySelectorAll('.timeincourt, [data-hour]')
            ).filter(function(el) {
                var r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) return false;
                var txt = (el.innerText || '').trim();
                return txt === tijd || txt.startsWith(tijd);
            }).map(function(el) {
                var r = el.getBoundingClientRect();
                return { el: el, absY: r.top + window.scrollY + r.height / 2 };
            });

            window._tijdCount = tijdItems.length;

            if (!tijdItems.length || !padelItems.length) return null;

            // ── Stap 3: kies tijdcel dichtstbij een padel-label ──────────────────
            var beste = null, minAfstand = Infinity, bestePadel = '';
            tijdItems.forEach(function(ti) {
                padelItems.forEach(function(pi) {
                    var afstand = Math.abs(ti.absY - pi.absY);
                    if (afstand < minAfstand) {
                        minAfstand = afstand;
                        beste      = ti.el;
                        bestePadel = pi.name;
                    }
                });
            });

            window._minAfstand = minAfstand;
            window._bestePadel = bestePadel;

            // Max 120px afwijking = zelfde rij (rijen zijn typisch 40-60px hoog)
            if (beste && minAfstand < 120) {
                return { cel: beste, baan: bestePadel };
            }
            return null;
        """, tijd, PADEL_BANEN)

        # Diagnose loggen (geen backslash in f-string: Python<3.12 compatibel)
        try:
            d_padel  = driver.execute_script('return window._padelCount||0')
            d_y      = driver.execute_script('return (window._padelAbsY||[]).slice(0,6)')
            d_cellen = driver.execute_script('return window._tijdCount||0')
            d_afst   = driver.execute_script('return Math.round(window._minAfstand||-1)')
            d_padnm  = driver.execute_script('return window._bestePadel||""')
            log.info(f"  diagnose: padel_labels={d_padel} absY={d_y} "
                     f"tijdcellen={d_cellen} minAfstand={d_afst} bestePadel='{d_padnm}'")
        except Exception:
            pass

        if not result:
            log.info(f"  Geen padel tijdslot '{tijd}' gevonden (bezet of buiten drempel)")
            continue

        # result is een dict {cel: WebElement, baan: 'Padel N'}
        cel  = result.get('cel') if isinstance(result, dict) else result
        baan = result.get('baan', '') if isinstance(result, dict) else ''

        if not cel:
            log.info(f"  Geen cel in result voor tijdslot '{tijd}'")
            continue

        # Log elementinfo en scroll cel in beeld
        try:
            info = driver.execute_script("""
                var el = arguments[0];
                el.scrollIntoView({block:'center', behavior:'instant'});
                return el.tagName + ' class=' + (el.className||'')
                       + ' txt=' + (el.innerText||'').trim().slice(0,30)
                       + ' html=' + el.outerHTML.slice(0,150);
            """, cel)
            log.info(f"  Tijdslot element: {info}")
        except Exception:
            pass

        time.sleep(0.5)
        # NIET _sluit_cookie_banner() aanroepen hier: de cookie-banner is al gesloten
        # en find_elements() wacht met implicit_wait=5s per XPATH = 25s voor niets.

        # ── Klik via ActionChains (real mouse event, NIET JS click) ──────────
        try:
            ActionChains(driver).move_to_element(cel).click().perform()
            log.info(f"  ✅ ActionChains klik op {tijd}, baan={baan}")
        except Exception as e:
            log.warning(f"  ActionChains mislukt ({e}), fallback JS click")
            try:
                driver.execute_script("arguments[0].click();", cel)
                log.info(f"  JS click als fallback uitgevoerd")
            except Exception as e2:
                log.warning(f"  JS click ook mislukt: {e2}")

        time.sleep(2)
        screenshot(driver, "10_baan_geselecteerd")

        # ── Controleer of de selectie geregistreerd is ────────────────────────
        # Na een geldige klik op een tijdslot verandert de klasse (bijv. 'selected')
        # of verschijnen er foutmeldingen. Log de celstatus en controleer pagina.
        selectie_ok = driver.execute_script("""
            var cel      = arguments[0];
            var padelNamen = arguments[1];
            var tijd     = arguments[2];
            try {
                var cls = (cel.className || '');
                var selected = cls.indexOf('selected') >= 0
                            || cls.indexOf('active')   >= 0
                            || cls.indexOf('chosen')   >= 0;
                // Controleer ook of er een foutbericht zichtbaar is
                var foutEls = document.querySelectorAll('.alert, .error, .warning, [class*="fout"], [class*="error"]');
                var foutTekst = '';
                for (var i = 0; i < foutEls.length; i++) {
                    if (foutEls[i].offsetParent && (foutEls[i].innerText||'').trim()) {
                        foutTekst = foutEls[i].innerText.trim().slice(0,100);
                        break;
                    }
                }
                return { cls: cls, selected: selected, fout: foutTekst };
            } catch(e) { return { cls: 'error', selected: false, fout: e.message }; }
        """, cel, PADEL_BANEN, tijd)
        log.info(f"  Selectiestatus: cls='{selectie_ok.get('cls','')}' "
                 f"selected={selectie_ok.get('selected',False)} "
                 f"fout='{selectie_ok.get('fout','')}'")

        try:
            body_na = driver.find_element(By.TAG_NAME, "body").text
            log.info(f"  Body na klik (500): {body_na[:500]}")
        except Exception:
            pass

        log.info(f"✅ Tijdslot {tijd} geselecteerd, baan={baan}")
        return baan, tijd

    log.error("❌ Geen beschikbaar padel tijdslot gevonden!")
    screenshot(driver, "baan_fout")
    return "", ""


# ── STAP 6: Bevestigen ────────────────────────────────────────────────────────
def _submit_knop(driver: uc.Chrome, knop) -> str:
    """Dien een form in via requestSubmit → form.submit() → ActionChains → JS click."""
    methode = driver.execute_script("""
        var btn  = arguments[0];
        var form = btn.closest('form');
        if (form && form.requestSubmit) {
            try { form.requestSubmit(btn); return 'requestSubmit'; }
            catch(e) {}
        }
        if (form) { form.submit(); return 'form.submit'; }
        btn.click(); return 'btn.click';
    """, knop)
    if methode in ('requestSubmit', 'form.submit', 'btn.click'):
        return methode
    # Extra fallback: ActionChains
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", knop)
        time.sleep(0.3)
        ActionChains(driver).move_to_element(knop).click().perform()
        return 'ActionChains'
    except Exception:
        driver.execute_script("arguments[0].click();", knop)
        return 'js.click.fallback'


def bevestig(driver: uc.Chrome) -> bool:
    """
    Stap 6: klik Volgende → ga naar bevestigingspagina → klik 'Bevestigen'.

    De bevestigingsknop is een <a id="confirmReservationButton"
    data-url="/Ajax/Profile/SaveReservation" data-redirect="/me/Reservations">.
    Geen form — de knop triggert een AJAX-call via een jQuery click-handler.

    Aanpak (volgorde):
      A) ActionChains klik op de knop → triggert jQuery handler → AJAX → redirect
      B) jQuery.ajax() direct aanroepen als A niet werkt
    Na elke poging wacht we tot de URL weg is van ReservationsConfirm (max 25s).
    """
    log.info("Bevestigen...")

    def _wacht_op_redirect(max_sec=25):
        """
        True als de URL niet langer ReservationsConfirm is binnen max_sec seconden.
        LET OP: check op 'ReservationsConfirm', NIET op 'ReservationsCourt' —
        want we starten al op de Confirm-pagina en die URL bevat al geen 'Court'.
        """
        try:
            WebDriverWait(driver, max_sec).until(
                lambda d: "ReservationsConfirm" not in d.current_url
            )
            return True
        except TimeoutException:
            return False

    try:
        # ── Stap 1: Volgende → bevestigingspagina ───────────────────────────
        url_voor = driver.current_url
        volgende = _zoek_knop(driver, ["Volgende", "Next"])
        if volgende:
            methode = _submit_knop(driver, volgende)
            log.info(f"  Volgende submit methode: {methode}")
            # Wacht op URL-verandering (max 8s) zodat we niet te vroeg lezen
            try:
                WebDriverWait(driver, 8).until(
                    lambda d: d.current_url != url_voor
                )
            except TimeoutException:
                pass
            time.sleep(1)
            screenshot(driver, "11_bevestig_pagina")
            url_na_vol = driver.current_url
            log.info(f"  URL na Volgende: {url_na_vol}")
            try:
                log.info(f"  Body na Volgende (400): "
                         f"{driver.find_element(By.TAG_NAME,'body').text[:400]}")
            except Exception:
                pass

            # Controleer of we op de juiste pagina zijn (ReservationsConfirm)
            if "ReservationsConfirm" not in url_na_vol:
                log.error(f"❌ Volgende bracht ons naar {url_na_vol} i.p.v. ReservationsConfirm "
                          f"— court-selectie mogelijk niet geregistreerd")
                screenshot(driver, "bevestig_fout_verkeerde_pagina")
                return False

        # ── Stap 2: zoek confirmReservationButton (op id of data-url) ───────
        knop_info = driver.execute_script("""
            var btn = document.getElementById('confirmReservationButton')
                   || document.querySelector('[data-url*="SaveReservation"]')
                   || document.querySelector('[data-url*="Confirm"]');
            if (!btn) return null;
            return {
                id:       btn.id,
                dataUrl:  btn.getAttribute('data-url'),
                redirect: btn.getAttribute('data-redirect'),
                html:     btn.outerHTML.slice(0, 300)
            };
        """)

        if not knop_info:
            log.error("❌ confirmReservationButton niet gevonden via id/data-url")
            try:
                log.error(f"Paginatekst: {driver.find_element(By.TAG_NAME,'body').text[:600]}")
            except Exception:
                pass
            screenshot(driver, "bevestig_fout")
            return False

        log.info(f"  Knop gevonden: id={knop_info.get('id')} "
                 f"data-url={knop_info.get('dataUrl')} "
                 f"redirect={knop_info.get('redirect')}")
        log.info(f"  HTML: {knop_info.get('html')}")

        data_url = knop_info.get('dataUrl', '')
        redirect = knop_info.get('redirect', '/me/Reservations')

        if not data_url:
            log.error("❌ data-url attribuut ontbreekt op bevestig-knop")
            screenshot(driver, "bevestig_fout")
            return False

        # ── Stap 3A: Intercept jQuery handler → haal POST-params op ─────────
        # De site's jQuery click-handler op de bevestig-knop stuurt de boeking-
        # data (court-id, datum, spelers) mee als POST-body. We:
        #   1. Overschrijven jQuery.ajax tijdelijk om de params te onderscheppen.
        #   2. Triggeren de knop via jQuery .trigger('click').
        #   3. Sturen de opgeslagen params nogmaals als echte POST met redirect.
        log.info("  Poging A: jQuery-trigger + intercept POST-params...")
        intercepted = driver.execute_script("""
            var targetUrl = arguments[0];
            window._interceptedData = null;
            window._interceptedCalled = false;

            if (!window.jQuery) return 'no-jQuery';

            // Overschrijf jQuery.ajax tijdelijk om de POST-params te vangen
            var origAjax = window.jQuery.ajax.bind(window.jQuery);
            window.jQuery.ajax = function(settings) {
                if (settings && settings.url &&
                    settings.url.indexOf('SaveReservation') >= 0) {
                    window._interceptedData  = settings.data || null;
                    window._interceptedCalled = true;
                    // Herstel direct: het werkelijke verzoek laten we via origAjax lopen
                    window.jQuery.ajax = origAjax;
                    return origAjax(settings);
                }
                window.jQuery.ajax = origAjax;
                return origAjax(settings);
            };

            // Installeer ook globale success/error hooks voor logging
            window._ajaxResponse = null;
            window._ajaxStatus   = null;
            window.jQuery(document).one('ajaxSuccess', function(e, xhr, settings) {
                if (settings.url && settings.url.indexOf('SaveReservation') >= 0) {
                    window._ajaxResponse = xhr.responseText.slice(0,300);
                    window._ajaxStatus   = 'ok:' + xhr.status;
                }
            });
            window.jQuery(document).one('ajaxError', function(e, xhr, settings) {
                if (settings.url && settings.url.indexOf('SaveReservation') >= 0) {
                    window._ajaxResponse = xhr.responseText.slice(0,300);
                    window._ajaxStatus   = 'err:' + xhr.status;
                }
            });

            // Trigger de jQuery-click op de knop (vuurde de handler)
            window.jQuery('#confirmReservationButton').trigger('click');
            return 'jQuery-trigger';
        """, data_url)
        log.info(f"  Intercept result: {intercepted}")
        time.sleep(3)   # geef de AJAX-call tijd om te sturen

        # Lees de onderschepte POST-data en AJAX-respons
        intercepted_data  = driver.execute_script("return window._interceptedData;")
        intercepted_called = driver.execute_script("return window._interceptedCalled;")
        ajax_response     = driver.execute_script("return window._ajaxResponse;")
        ajax_status       = driver.execute_script("return window._ajaxStatus;")
        log.info(f"  Onderschept: called={intercepted_called} data={intercepted_data}")
        log.info(f"  AJAX response: status={ajax_status} body={ajax_response}")

        # Controleer op server-side fout: "Niet gevonden" = boeking afgewezen
        if ajax_response and (
            "niet gevonden" in ajax_response.lower()
            or "not found" in ajax_response.lower()
        ):
            log.error(f"  ❌ Server wees boeking af (Poging A): '{ajax_response}' — "
                      f"boeking NIET aangemaakt. Controleer of je al een actieve reservering hebt.")
            screenshot(driver, "bevestig_server_fout")
            return False

        # Wacht op redirect (kan al gebeurd zijn via de site's eigen success-callback)
        if _wacht_op_redirect(5):
            url_na = driver.current_url
            try:
                body_a = driver.find_element(By.TAG_NAME, "body").text
                log.info(f"  Body na bevestiging A (600): {body_a[:600]}")
            except Exception:
                pass
            log.info(f"✅ Bevestigd via jQuery-trigger! Redirect naar {url_na}")
            screenshot(driver, "12_na_bevestiging")
            return True

        url_na = driver.current_url
        log.warning(f"  Poging A geen redirect — URL: {url_na}")

        # ── Stap 3B: jQuery.ajax() met onderschepte params (of leeg) ──────────
        log.warning("  Poging B: jQuery.ajax() met POST-data naar SaveReservation...")
        ajax_start = driver.execute_script("""
            var url      = arguments[0];
            var redirect = arguments[1];
            var postData = arguments[2];   // onderschepte params of null
            window._bevestigFout    = null;
            window._bevestigStatus  = null;

            function doeRedirect() {
                window.location.href = redirect || '/me/Reservations';
            }

            var ajaxOpts = {
                url:       url,
                type:      'POST',
                xhrFields: { withCredentials: true },
                success: function(data, status, xhr) {
                    window._bevestigStatus   = 'ok:' + xhr.status;
                    window._bevestigResponse = (data || xhr.responseText || '').slice(0,300);
                    // Controleer op server-side fout in de body (HTTP 200 maar inhoud = fout)
                    var bodyLower = window._bevestigResponse.toLowerCase();
                    if (bodyLower.indexOf('niet gevonden') >= 0 ||
                        bodyLower.indexOf('not found') >= 0) {
                        window._bevestigStatus = 'error:not-found';
                        window._bevestigFout   = window._bevestigResponse;
                    } else {
                        doeRedirect();
                    }
                },
                error: function(xhr, textStatus, err) {
                    window._bevestigFout   = xhr.status + ' ' + textStatus
                                             + ' ' + xhr.responseText.slice(0,200);
                    window._bevestigStatus = 'error';
                }
            };
            if (postData) { ajaxOpts.data = postData; }

            if (window.jQuery) {
                window.jQuery.ajax(ajaxOpts);
                return 'jQuery.ajax' + (postData ? '+data' : '-nodata');
            }

            fetch(url, {
                method:      'POST',
                credentials: 'include',
                headers:     { 'X-Requested-With': 'XMLHttpRequest' }
            }).then(function(r) {
                window._bevestigStatus = 'fetch:' + r.status;
                if (r.ok) { doeRedirect(); }
                else { r.text().then(function(t) { window._bevestigFout = t.slice(0,200); }); }
            }).catch(function(e) {
                window._bevestigFout   = e.message;
                window._bevestigStatus = 'fetch-error';
            });
            return 'fetch';
        """, data_url, redirect, intercepted_data)
        log.info(f"  AJAX gestart via: {ajax_start}")

        if _wacht_op_redirect(25):
            url_na2 = driver.current_url
            b_resp   = driver.execute_script("return window._bevestigResponse||'';")
            b_status = driver.execute_script("return window._bevestigStatus||'';")
            b_fout   = driver.execute_script("return window._bevestigFout||'';")
            log.info(f"  AJAX B response: status={b_status} body={b_resp[:200]}")
            try:
                body_confirm2 = driver.find_element(By.TAG_NAME, "body").text
                log.info(f"  Body na bevestiging B (600): {body_confirm2[:600]}")
            except Exception:
                pass

            # Controleer of Poging B ook een fout terugkreeg
            if b_status == 'error:not-found' or (
                b_fout and (
                    "niet gevonden" in b_fout.lower()
                    or "not found" in b_fout.lower()
                )
            ):
                log.error(f"  ❌ Server wees boeking ook af (Poging B): '{b_fout or b_resp}' — "
                          f"boeking NIET aangemaakt.")
                screenshot(driver, "bevestig_server_fout_b")
                return False

            log.info(f"✅ Bevestigd via jQuery.ajax+data! Redirect naar {url_na2}")
            screenshot(driver, "12_na_bevestiging")
            return True

        fout   = driver.execute_script("return window._bevestigFout || '(geen fout)';")
        status = driver.execute_script("return window._bevestigStatus || '(onbekend)';")
        url_na2 = driver.current_url
        try:
            body_na2 = driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            body_na2 = ""
        log.error(f"❌ Bevestigen definitief mislukt — "
                  f"status={status} fout={fout} url={url_na2}")
        log.error(f"   Body: {body_na2[:400]}")
        screenshot(driver, "bevestig_fout")
        return False

    except Exception as e:
        log.error(f"❌ Bevestigen mislukt (exception): {e}")
        screenshot(driver, "bevestig_fout")
        return False


# ── STAP 7: Verificatie ───────────────────────────────────────────────────────
def verifieer_boeking(driver: uc.Chrome, datum: str, tijd: str) -> str:
    """
    Controleer of de boeking zichtbaar is op de reserveringspagina.
    Probeert zowel /mijn/Reservations als /me/Reservations.
    Geeft de naam van de geboekte baan terug (bijv. 'Padel 1'), of '' als niet gevonden.
    """
    log.info("Boeking verifiëren...")

    datum_obj  = datetime.strptime(datum, "%Y-%m-%d")
    datum_nl   = f"{datum_obj.day}-{datum_obj.month}"   # bijv. "29-5"
    datum_nl2  = f"{datum_obj.day} mei"                  # bijv. "29 mei"
    datum_nl3  = f"{datum_obj.day:02d}-{datum_obj.month:02d}-{datum_obj.year}"  # "29-05-2026"
    # Let op: gebruik GEEN losse tijdstring als zoekterm — die matcht ook op boekingen
    # van andere datums (bijv. een bestaande boeking op een andere dag om 15:00).
    # Vereiste: datum ÉN tijd moeten allebei aanwezig zijn op de pagina.
    datum_tekens = [datum, datum_nl, datum_nl2, datum_nl3]

    def _check_pagina(url: str, scherm_naam: str) -> str:
        try:
            driver.get(url)
            time.sleep(5)   # geef AJAX-content tijd om te laden
            screenshot(driver, scherm_naam)
            body = driver.find_element(By.TAG_NAME, "body").text
            log.info(f"  {url} body (800): {body[:800]}")

            # Verificatie: datum én tijd moeten allebei aanwezig zijn
            datum_ok = any(t in body for t in datum_tekens)
            tijd_ok  = tijd in body
            if datum_ok and tijd_ok:
                baan_naam = next((b for b in PADEL_BANEN if b in body), "")
                log.info(f"✅ Boeking BEVESTIGD op {url}! baan={baan_naam or '(onbekend)'}")
                return baan_naam or "Padel"

            log.info(f"  Boeking NIET gevonden op {url} "
                     f"(datum_ok={datum_ok} tijd_ok={tijd_ok} "
                     f"datum_tekens={datum_tekens} tijd='{tijd}')")
            return ""
        except Exception as e:
            log.warning(f"  Verificatie fout op {url}: {e}")
            return ""

    # Probeer eerst /mijn/Reservations (Mijn Boekingen-overzicht)
    baan = _check_pagina("https://www.etv-volley.nl/mijn/Reservations",
                         "13_mijn_reserveringen")
    if baan:
        return baan

    # Probeer /me/Reservations (wizard-startpagina, toont ook huidige boeking)
    baan = _check_pagina("https://www.etv-volley.nl/me/Reservations",
                         "13b_me_reserveringen")
    if baan:
        return baan

    log.error(f"❌ Boeking NIET zichtbaar op beide reserveringspagina's!")
    log.error(f"   Gezocht op: {boek_tekens}")
    return ""


# ── Main ──────────────────────────────────────────────────────────────────────
def _zet_in_wachtrij(datum: str, tijd: str, speler2: str, speler3: str, speler4: str) -> bool:
    """
    Schrijf een wachtrij-bestand voor latere verwerking en push naar de repo.
    Wordt gebruikt als de speeldatum nog meer dan 2 dagen weg ligt — de
    verwerk_wachtrij.yml workflow pikt het bestand op om 07:00 NL op de boekingsdatum
    en triggert boek.yml opnieuw met deze inputs.
    """
    import subprocess
    tijd_slug = tijd.replace(":", "")
    bestand = f"wachtrij/{datum}_{tijd_slug}.json"
    payload = {
        "datum":     datum,
        "tijd":      tijd,
        "spelers":   [SPELER1, speler2, speler3, speler4],
        "ingediend": datetime.now().isoformat(timespec="seconds"),
    }
    os.makedirs("wachtrij", exist_ok=True)
    with open(bestand, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    log.info(f"📥 Wachtrij-bestand geschreven: {bestand}")

    try:
        subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
        subprocess.run(["git", "config", "user.name",  "knltb-autoboek-bot"], check=True)
        subprocess.run(["git", "add", bestand], check=True)
        subprocess.run(["git", "commit", "-m", f"wachtrij: voeg {datum} om {tijd} toe"], check=True)
        subprocess.run(["git", "push"], check=True)
        log.info("✅ Wachtrij-bestand gecommit en gepusht naar repo")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"❌ Git push voor wachtrij mislukt: {e}")
        return False


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

    # Boekingsstrategie: vanaf 07:00 op (speeldatum - 2 kalenderdagen) mag worden geboekt.
    # Dat geldt voor alle dagdelen van dag 0, dag+1 en dag+2.
    nu            = datetime.now()
    boekingsdatum = speeldatum - timedelta(days=2)
    dag_verschil  = (speeldatum.date() - nu.date()).days
    log.info(f"📅 Speeldatum dag+{dag_verschil} | boekingsdatum: {boekingsdatum.strftime('%d-%m-%Y')} om 07:00")

    if nu.date() < boekingsdatum.date():
        log.info(f"⏳ Te vroeg om direct te boeken — speeldatum is over {dag_verschil} dagen. "
                 f"Boekingsdatum: {boekingsdatum.strftime('%d-%m-%Y')} om 07:00 NL.")
        log.info("📥 Zet in wachtrij voor automatische boeking op de boekingsdatum.")
        if _zet_in_wachtrij(args.datum, args.tijd, args.speler2, args.speler3, args.speler4):
            log.info(f"✅ In wachtrij gezet — verwerk_wachtrij workflow start de boeking "
                     f"automatisch op {boekingsdatum.strftime('%d-%m-%Y')} om 07:00 NL.")
            sys.exit(0)
        log.error("❌ Kon wachtrij-bestand niet opslaan — boeking NIET ingepland")
        sys.exit(1)
    elif nu.date() == boekingsdatum.date() and (nu.hour < 7 or (nu.hour == 7 and nu.minute < 1)):
        doel = boekingsdatum.replace(hour=7, minute=1, second=0, microsecond=0)
        wacht_sec = int((doel - nu).total_seconds())
        log.info(f"⏳ Wacht {wacht_sec} sec tot 07:01 NL op boekingsdatum "
                 f"{boekingsdatum.strftime('%d-%m-%Y')} (buffer voor server-klokverschil)...")
        time.sleep(wacht_sec)
    else:
        log.info(f"✅ Boeken! (dag+{dag_verschil}, boekingsdatum bereikt)")

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

        # ── Verificeer dat boeking zichtbaar is op Mijn Reserveringen ────────
        geverifieerde_baan = verifieer_boeking(driver, args.datum, geboekte_tijd)
        if not geverifieerde_baan:
            log.error("🚫 Boeking niet zichtbaar op reserveringspagina — agenda NIET bijgewerkt")
            sys.exit(1)

        # Gebruik geverifieerde baan-naam (betrouwbaarder dan detectie tijdens grid-klik)
        baan = geverifieerde_baan

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

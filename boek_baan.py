"""
ETV Volley Baan Auto-Reservering
Automatisch een padelbaan reserveren via etv-volley.nl/mijn
Het Google Agenda-event wordt niet hier aangemaakt, maar door
lees_reserveringen.py (getriggerd via beheer_reserveringen.yml
na een succesvolle boeking) -- zie maak_ontbrekende_agenda_items().

Omgevingsvariabelen (GitHub Secrets):
  ETVVOLLEY_BONDSNUMMER               - Jouw bondsnummer / gebruikersnaam
  ETVVOLLEY_WACHTWOORD                - Jouw wachtwoord
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_AMS = ZoneInfo("Europe/Amsterdam")

def _nu_nl() -> datetime:
    """Huidige tijd in NL (Amsterdam), als naive datetime voor vergelijking met andere naive datetimes."""
    return datetime.now(tz=_AMS).replace(tzinfo=None)

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
logging.getLogger("undetected_chromedriver").setLevel(logging.WARNING)

# â"€â"€ Instellingen â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
LOGIN_URL    = "https://www.etv-volley.nl/mijn"
RESERVEER_URL = "https://www.etv-volley.nl/mijn/Reservations"

BONDSNUMMER  = os.environ.get("ETVVOLLEY_BONDSNUMMER", "")
WACHTWOORD   = os.environ.get("ETVVOLLEY_WACHTWOORD", "")
GEBRUIKER    = os.environ.get("GEBRUIKER", "joris")
SPELER1      = os.environ.get("SPELER1_NAAM", "Joris van den Broek")

PADEL_BANEN   = ["Padel 1", "Padel 2", "Padel 3", "Padel 4", "Padel 5", "Padel 6"]
TENNIS_BANEN  = ["Tennis 04", "Tennis 05", "Tennis 06", "Tennis 07",
                 "Tennis 08", "Tennis 09", "Tennis 11", "Tennis 12"]
WACHT_TIMEOUT = 15

_boek_etv_reden = ""  # set by bevestig() when ETV body contains a limit/error message


def _schrijf_boekstatus(status: str, reden: str, datum: str = "", tijd: str = "",
                        sport: str = "", spelers: list = None, baan: str = "") -> None:
    """Schrijf boekstatus_<gebruiker>.json voor weergave in de PWA."""
    try:
        nu_str = datetime.now(tz=_AMS).isoformat(timespec="seconds")
        data = {
            "status": status,
            "reden": reden,
            "datum": datum,
            "tijd": tijd,
            "sport": sport,
            "spelers": spelers or [],
            "baan": baan,
            "tijdstip": nu_str,
        }
        pad = f"boekstatus_{GEBRUIKER}.json"
        with open(pad, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log.info(f"Boekstatus geschreven: {status} — {reden}")
    except Exception as e:
        log.warning(f"_schrijf_boekstatus mislukt: {e}")
# â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def dagdeel(tijd: str) -> str:
    uur = int(tijd.split(":")[0])
    if uur < 12:   return "Ochtend"
    elif uur < 17: return "Middag"
    else:          return "Avond"


def genereer_tijden(voorkeur_tijd: str) -> list:
    """Genereer tijden rondom voorkeur, 30 min stappen, beperkt tot hetzelfde dagdeel."""
    DAGDEEL_GRENZEN = {"Ochtend": ("08:00", "11:30"), "Middag": ("12:00", "16:30"), "Avond": ("17:00", "22:00")}
    dd = dagdeel(voorkeur_tijd)
    vroegst = datetime.strptime(DAGDEEL_GRENZEN[dd][0], "%H:%M")
    laatst  = datetime.strptime(DAGDEEL_GRENZEN[dd][1], "%H:%M")
    basis   = datetime.strptime(voorkeur_tijd, "%H:%M")
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


# â"€â"€ Selenium driver â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
def chrome_major_versie() -> int | None:
    """Detecteer de geÃ¯nstalleerde Chrome major versie zodat UC de juiste driver downloadt."""
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
    log.debug("Chrome versie niet detecteerbaar  UC bepaalt zelf de driver versie")
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
    log.debug(f" Screenshot: {naam}.png | URL: {driver.current_url}")


def _log_zichtbare_spelers(driver, spelers, label: str):
    """
    Diagnose: log of de verwachte spelers visueel op de huidige pagina staan.

    LET OP: ETV toont de spelerslijst ALLEEN op ReservationsPlayers en
    ReservationsConfirm. Op ReservationsDay/Court is 0/4 zichtbaar = normaal,
    geen reden tot paniek. Daarom: WARNING-level alleen op pagina's waar de
    spelers daadwerkelijk zichtbaar moeten zijn.
    """
    url = driver.current_url or ""
    spelers_zichtbaar_pagina = (
        "ReservationsPlayers" in url
        or "ReservationsConfirm" in url
        or "/mijn/Reservations" in url
        or ("/me/Reservations" in url and "ReservationsCourt" not in url and "ReservationsDay" not in url)
    )

    try:
        body = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        body = ""
    counts = {s: body.count(s) for s in spelers}
    aanwezig = [s for s, c in counts.items() if c > 0]
    missend  = [s for s, c in counts.items() if c == 0]
    log.debug(f" SPELERS-CHECK [{label}] URL={url}")
    log.debug(f"    Aanwezig ({len(aanwezig)}/{len(spelers)}): {aanwezig}")
    if missend and spelers_zichtbaar_pagina:
        log.warning(f"    MIST ({len(missend)}): {missend}")


# â"€â"€ STAP 1: Inloggen â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
def login(driver: uc.Chrome) -> bool:
    # TODO: vervang door `from etv_common import login as _common_login` zodra
    # de huidige cron-flow stabiel bewezen is (>3 succesvolle runs zonder
    # spelers-mystery). lees_reserveringen.py en haal_leden_op.py gebruiken
    # die shared versie al; deze functie blijft voorlopig staan om het
    # kritieke booking-pad niet te raken vÃ³Ã³r veld-validatie.
    log.info(f"Navigeer naar {LOGIN_URL}")
    driver.get(LOGIN_URL)
    time.sleep(1)
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
            log.info(" Cookie-banner geaccepteerd")
            time.sleep(1)
            break
        except Exception:
            pass

    # Log alle input-velden voor diagnose
    try:
        alle_inputs = driver.find_elements(By.TAG_NAME, "input")
        log.debug(f"Gevonden input-velden ({len(alle_inputs)}):")
        for inp in alle_inputs:
            log.debug(f"  type={inp.get_attribute('type')} name={inp.get_attribute('name')} "
                      f"id={inp.get_attribute('id')} placeholder={inp.get_attribute('placeholder')} "
                      f"visible={inp.is_displayed()}")
    except Exception as e:
        log.debug(f"Input-veld scan mislukt: {e}")

    try:
        gebruiker_veld = wacht_op(driver, By.XPATH,
            "//input[@type='text' or @type='email' "
            "or @name='username' or @name='Username' or @name='UserName' "
            "or @id='username' or @id='Username' or @id='UserName' "
            "or contains(@placeholder,'bondsnummer') or contains(@placeholder,'gebruikersnaam') "
            "or contains(@placeholder,'e-mail') or contains(@placeholder,'email')]")
        log.debug(f"Gebruikersveld: name='{gebruiker_veld.get_attribute('name')}' "
                 f"id='{gebruiker_veld.get_attribute('id')}'")

        # Vul in via JS — triggert ook React/Vue native input events
        driver.execute_script("""
            var el = arguments[0], val = arguments[1];
            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, gebruiker_veld, BONDSNUMMER)
        log.debug(f"Bondsnummer ingevuld via JS ({len(BONDSNUMMER)} tekens)")

        ww_veld = wacht_op(driver, By.XPATH, "//input[@type='password']")
        log.debug(f"Wachtwoordveld: name='{ww_veld.get_attribute('name')}' "
                 f"id='{ww_veld.get_attribute('id')}'")

        driver.execute_script("""
            var el = arguments[0], val = arguments[1];
            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, ww_veld, WACHTWOORD)
        log.debug(f"Wachtwoord ingevuld via JS ({len(WACHTWOORD)} tekens)")

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
            log.warning("Geen submit-knop gevonden  gebruik Keys.RETURN als fallback")
            ww_veld.send_keys(Keys.RETURN)

        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.current_url.rstrip('/') != LOGIN_URL.rstrip('/')
            )
        except TimeoutException:
            pass
        time.sleep(0.5)
        screenshot(driver, "02_na_login")
        log.info(f"URL na login: {driver.current_url}")

        # Log paginatekst voor foutmeldingen
        try:
            body_tekst = driver.find_element(By.TAG_NAME, "body").text
            for zoekterm in ["onjuist", "ongeldig", "fout", "incorrect", "error",
                             "geblokkeerd", "locked", "account", "blocked", "te veel"]:
                if zoekterm in body_tekst.lower():
                    log.warning(f" '{zoekterm}' gevonden in paginatekst")
            log.info(f"Paginatitel na login: {driver.title}")
            log.debug(f"Paginatekst (eerste 500): {body_tekst[:500]}")
        except Exception:
            pass

        # Controleer of wachtwoordveld nog zichtbaar is (= login mislukt)
        try:
            pw = driver.find_element(By.XPATH, "//input[@type='password']")
            if pw.is_displayed():
                log.error(" Inloggen mislukt  wachtwoordveld nog zichtbaar")
                screenshot(driver, "02b_login_mislukt")
                return False
        except Exception:
            pass  # Veld weg = inloggen gelukt

        log.info(" Ingelogd!")
        return True
    except TimeoutException as e:
        # Detecteer onderhoudspagina: geen inputvelden + onderhoud-tekst
        try:
            body = driver.find_element(By.TAG_NAME, "body").text.lower()
            onderhoud_keywords = ["onderhoud", "maintenance", "tijdelijk niet beschikbaar",
                                  "temporarily unavailable", "we zijn zo weer bij je terug",
                                  "be right back"]
            if any(kw in body for kw in onderhoud_keywords):
                log.warning(" ETV toont onderhoudspagina  site tijdelijk niet beschikbaar")
                screenshot(driver, "login_fout_onderhoud")
                return 'ONDERHOUD'
        except Exception:
            pass
        log.error(f" Inloggen mislukt: {e}")
        screenshot(driver, "login_fout")
        return False


# â"€â"€ STAP 2: Baan afhangen klikken â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
def klik_baan_afhangen(driver: uc.Chrome) -> bool:
    log.info("Navigeer naar reserveringspagina...")
    driver.get(RESERVEER_URL)
    try:
        WebDriverWait(driver, 10).until(
            lambda d: len(d.find_element(By.TAG_NAME, "body").text) > 50
        )
    except TimeoutException:
        pass
    try:
        afhangen_knop = wacht_op(driver, By.XPATH,
            "//a[contains(text(),'Baan afhangen') or contains(text(),'afhangen')] "
            "| //button[contains(text(),'Baan afhangen') or contains(text(),'afhangen')]")
        afhangen_knop.click()
        time.sleep(2)
        log.info(" 'Baan afhangen' geklikt")
        return True
    except TimeoutException as e:
        log.error(f" 'Baan afhangen' knop niet gevonden: {e}")
        screenshot(driver, "afhangen_fout")
        return False


# â"€â"€ Navigatie-hulpfunctie â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

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


# â"€â"€ STAP 3: Spelers toevoegen â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€

def _zoek_veld_spelers(driver: uc.Chrome):
    """Geef het eerste zichtbare text/search-input terug op de spelerspagina."""
    alle = driver.find_elements(By.XPATH, "//input[@type='text' or @type='search']")
    for inp in alle:
        if inp.is_displayed() and inp.is_enabled():
            log.debug(f"  Zoekveld: placeholder='{inp.get_attribute('placeholder')}' "
                      f"id='{inp.get_attribute('id')}'")
            return inp
    return None


def _ruim_onverwachte_spelers_op(driver: uc.Chrome, verwachte_data_ids: set) -> list:
    """
    Scan #youPlayWith. Elke entry met een data-id die NIET in
    verwachte_data_ids zit, wordt verwijderd via een klik op de Ã— knop
    (`a.removePlayer[data-id=...]`).

    Achtergrond: bij zoekterm "Daniel Enderink" toont ETV's typeahead Ã³Ã³k
    substring-matches zoals "Ellen Daniels" en "Danse Cleij". In runs #68
    en #69 verschenen die OOK in #youPlayWith zonder dat het script erop
    klikte — vermoedelijk via een hover-/focus-event in de typeahead-flow.
    Resultaat: #youPlayWith zit vol (max 3) voor we onze 3 gewenste spelers
    erin krijgen â†’ volgende speler kan niet meer worden toegevoegd.

    Deze helper draait NA elke succesvolle speler-add en ruimt eventuele
    mystery-toevoegingen op. Werkt ook als startpunt-cleanup bij stale
    state uit een vorige booking-poging.

    Returns: lijst met namen die zijn verwijderd (voor logging).
    """
    verwijderd = []
    try:
        onverwachte = driver.execute_script("""
            var verwacht = arguments[0];
            var verwachtSet = {};
            for (var i = 0; i < verwacht.length; i++) verwachtSet[verwacht[i]] = true;

            var c = document.getElementById('youPlayWith');
            if (!c) return [];
            var rems = c.querySelectorAll('a.removePlayer[data-id], [data-id]');
            var out = [];
            for (var i = 0; i < rems.length; i++) {
                var did = rems[i].getAttribute('data-id');
                if (!did || verwachtSet[did]) continue;
                // naam: dichtstbijzijnde h6, of innerText van parent li
                var li = rems[i].closest('li') || rems[i].parentElement;
                var h6 = li ? li.querySelector('h6') : null;
                var naam = h6 ? h6.innerText.trim() : (li ? li.innerText.trim() : '?');
                out.push({dataId: did, naam: naam});
            }
            return out;
        """, list(verwachte_data_ids))

        for item in onverwachte or []:
            did = item.get('dataId')
            naam = item.get('naam', '?')
            log.debug(f"   Onverwachte speler in #youPlayWith: '{naam}' "
                      f"(data-id={did}) — wordt verwijderd")
            try:
                # jQuery .trigger('click') werkt voor ETV's verwijder-handler;
                # zelfde patroon als de speler-toevoegen fallback.
                ok = driver.execute_script("""
                    var sel = 'a.removePlayer[data-id="' + arguments[0] + '"]';
                    if (window.jQuery) {
                        var $el = window.jQuery(sel);
                        if ($el.length) { $el.trigger('click'); return 'jquery'; }
                    }
                    var el = document.querySelector(sel);
                    if (el) { el.click(); return 'dom'; }
                    return 'niet gevonden';
                """, did)
                time.sleep(0.8)
                # Verifieer dat 'ie weg is
                weg = driver.execute_script("""
                    return !document.querySelector('a.removePlayer[data-id="' + arguments[0] + '"]');
                """, did)
                if weg:
                    log.debug(f"   Verwijderd via {ok}: '{naam}'")
                    verwijderd.append(naam)
                else:
                    log.debug(f"   '{naam}' nog steeds aanwezig na {ok}-klik")
            except Exception as e:
                log.error(f"  Kon onverwachte speler '{naam}' niet verwijderen: {e}")
    except Exception as e:
        log.debug(f"  Scan onverwachte spelers faalde: {e}")
    return verwijderd


def _voeg_speler_toe(driver: uc.Chrome, speler: str, index: int,
                      verwachte_data_ids: set) -> str:
    """
    Selecteer EXCLUSIEF de opgegeven speler — definitieve implementatie
    gebaseerd op echte ETV/KNLTB.Club HTML.

    verwachte_data_ids: set van data-ids die OK zijn in #youPlayWith
                        (eerder toegevoegde spelers). Na succesvolle add
                        wordt #youPlayWith opgeruimd: alles dat NIET in
                        (verwachte_data_ids âˆª {nieuwe data-id}) staat,
                        wordt verwijderd.

    Returns: data-id (string) bij success, "" bij fail.

    HTML-structuur:

      <!-- zoekresultaten -->
      <div class="col-12 players searchresults">
        <div class="card mb-3">
          <div class="card-body addPlayer" data-id="UUID">
            Chris van Waardenburg
          </div>
        </div>
      </div>

      <!-- Recent mee gespeeld -->
      <div class="col-12 col-md-6 recentplayers">
        <div class="card-body addPlayer" data-id="UUID2">
          Peter Nijhof
        </div>
      </div>

      <!-- Na succesvolle add: -->
      <div id="youPlayWith">
        <li class="list-group-item">
          <h6>Chris van Waardenburg</h6>
          <a class="removePlayer" data-id="UUID">Ã—</a>     â† zelfde UUID
        </li>
      </div>

    Werkwijze:
    1. Type zoekterm
    2. Vind .addPlayer[data-id] card waarvan innerText exact gelijk is aan
       een geaccepteerde naamvorm. data-id wordt onthouden.
    3. Klik die card via ActionChains
    4. Verifieer dat #youPlayWith een element met DIE SPECIFIEKE data-id
       bevat. Niet alleen op naam, maar op de exacte UUID die we klikten.
       Zo voorkomen we ELKE vorm van verkeerde selectie — ook als ETV
       ooit een naam dubbel zou tonen.
    """
    woorden    = speler.split()
    achternaam = woorden[-1]

    # Acceptabele exacte naamvormen
    accepted = [speler]
    if len(woorden) >= 3:
        accepted.append(f"{woorden[0]} {achternaam}")

    def _vind_addplayer_data_id() -> tuple:
        """
        Vind in .searchresults of .recentplayers een .addPlayer[data-id]
        waarvan innerText EXACT gelijk is aan een geaccepteerde naamvorm.
        Returns (data_id, tekst) of (None, None).

        BELANGRIJK: returnt ALLEEN de data-id (string), niet het element.
        Element-refs die uit execute_script komen verstalen onmiddellijk
        wanneer de typeahead-DOM ververst — wat ETV doet binnen ~300ms.
        Door alleen het stabiele data-id terug te geven, kunnen we daarna
        het element VERS via Selenium opzoeken en direct klikken.
        """
        res = driver.execute_script("""
            var accepted = arguments[0];
            var containers = document.querySelectorAll(
                '.searchresults, .recentplayers'
            );
            for (var c = 0; c < containers.length; c++) {
                var cards = containers[c].querySelectorAll('.addPlayer[data-id]');
                for (var i = 0; i < cards.length; i++) {
                    var card = cards[i];
                    if (!card.offsetParent) continue;
                    var t = (card.innerText || '').replace(/\\s+/g, ' ').trim();
                    for (var j = 0; j < accepted.length; j++) {
                        if (t === accepted[j]) {
                            return { dataId: card.getAttribute('data-id'), tekst: t };
                        }
                    }
                }
            }
            return null;
        """, accepted)
        if not res:
            return (None, None)
        return (res.get('dataId'), res.get('tekst'))

    def _is_in_youplaywith(data_id: str) -> bool:
        """Check of #youPlayWith een element bevat met deze data-id."""
        try:
            return bool(driver.execute_script("""
                var doelId = arguments[0];
                var container = document.getElementById('youPlayWith');
                if (!container) return false;
                var els = container.querySelectorAll('[data-id]');
                for (var i = 0; i < els.length; i++) {
                    if (els[i].getAttribute('data-id') === doelId) return true;
                }
                return false;
            """, data_id))
        except Exception:
            return False

    zoek_veld = _zoek_veld_spelers(driver)
    if not zoek_veld:
        log.error(f"   Zoekveld niet gevonden voor '{speler}'")
        return ""

    # Zoektermen van specifiek naar breder. De data-id verificatie achteraf
    # garandeert dat we nooit een verkeerde speler boeken, zelfs als de
    # typeahead onverwacht reageert.
    zoektermen = [speler]
    if len(woorden) >= 3:
        zoektermen.append(f"{woorden[0]} {achternaam}")
    zoektermen.append(achternaam)

    for zoekterm in zoektermen:
        # Wis veld + typ via echte toetsaanslagen (typeahead-trigger)
        try:
            zoek_veld.click()
            zoek_veld.send_keys(Keys.CONTROL + "a")
            zoek_veld.send_keys(Keys.DELETE)
            time.sleep(0.3)
            zoek_veld.send_keys(zoekterm)
            log.debug(f"  Zoekterm: '{zoekterm}'")
        except Exception as e:
            log.warning(f"  Zoekveld input faalde ({e}), volgende term")
            zoek_veld = _zoek_veld_spelers(driver)
            if not zoek_veld:
                continue
            continue
        # Wacht tot er een .addPlayer[data-id] card verschijnt met EXACTE match
        try:
            WebDriverWait(driver, 8).until(
                lambda d: _vind_addplayer_data_id()[0] is not None
            )
        except TimeoutException:
            log.info(f"  Geen .addPlayer card met exacte naam-match na 8s")
            try:
                zoek_veld.send_keys(Keys.ESCAPE)
                time.sleep(0.3)
            except Exception:
                pass
            time.sleep(1.0)
            continue

        data_id, tekst = _vind_addplayer_data_id()
        if not data_id:
            continue
        log.debug(f"   Card gevonden: data-id={data_id}, tekst='{tekst}'")

        # Pre-klik check: staat deze speler AL in #youPlayWith? Dan was
        # 'ie in een vorige booking-poging al toegevoegd en blijft hangen
        # in ETV's session-state. Beschouw als success en ga door.
        if _is_in_youplaywith(data_id):
            log.info(f"   {speler} stond al in 'Je gaat spelen met' "
                     f"(leftover van eerdere booking-poging) — skip click")
            # Ruim eventuele mystery-spelers op
            _ruim_onverwachte_spelers_op(driver, verwachte_data_ids | {data_id})
            return data_id

        # Vind het element VERS via Selenium met de stabiele data-id.
        # JS-returns van execute_script verstalen meteen wanneer ETV's
        # typeahead de DOM ververst (gebeurt binnen ~300ms — bewezen in
        # run #61 waar alle 3 zoektermen StaleElementReferenceException
        # gaven). Selenium's eigen find_element returnt een live ref.
        try:
            el = driver.find_element(
                By.CSS_SELECTOR, f'.addPlayer[data-id="{data_id}"]'
            )
        except Exception as e:
            log.warning(f"  Element met data-id={data_id} niet gevonden: {e}")
            continue

        # â"€â"€ Klik-strategie met 3 fallbacks â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        # Run #64 (30-05 manueel-retry) bewees dat ActionChains-click niet
        # altijd ETV's jQuery-handler triggert: visible click, geen toevoeging
        # aan #youPlayWith. Daarom 3 strategieÃ«n met tussentijdse checks:
        #   1. ActionChains (echte muis-events, isTrusted=true)
        #   2. jQuery .trigger('click') — invokes alle jQuery-handlers ongeacht binding
        #   3. DOM element.click() — laatste redmiddel
        # Tussen elke stap kijken we of #youPlayWith de data-id nu bevat;
        # zo ja â†’ klaar.

        # Strategie 1: ActionChains
        try:
            ActionChains(driver).move_to_element(el).click().perform()
            log.debug(f"  ActionChains click op data-id={data_id}")
        except Exception as e:
            log.warning(f"  ActionChains faalde ({type(e).__name__})")
        time.sleep(1.0)

        # Strategie 2 (als 1 niet werkte): jQuery trigger
        if not _is_in_youplaywith(data_id):
            log.debug(f"  ActionChains registreerde niet  jQuery .trigger('click') fallback")
            try:
                driver.execute_script(
                    'if (window.jQuery) '
                    f'window.jQuery(\'.addPlayer[data-id="{data_id}"]\').trigger("click");'
                )
            except Exception as e:
                log.warning(f"  jQuery trigger faalde: {e}")
            time.sleep(1.5)

        # Strategie 3 (als 1+2 niet werkten): DOM click
        if not _is_in_youplaywith(data_id):
            log.info(f"  jQuery trigger ook geen effect  DOM element.click() fallback")
            try:
                driver.execute_script(
                    f'var el=document.querySelector(\'.addPlayer[data-id="{data_id}"]\'); '
                    f'if(el)el.click();'
                )
            except Exception as e:
                log.warning(f"  DOM click faalde: {e}")
            time.sleep(1.5)

        # â"€â"€ VERIFICATIE: #youPlayWith MOET deze data-id bevatten â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        verified = False
        for verif_poging in range(1, 5):
            if _is_in_youplaywith(data_id):
                verified = True
                if verif_poging > 1:
                    log.info(f"  Speler verschenen in youPlayWith na verifieer-poging {verif_poging}")
                break
            time.sleep(1.5)

        if verified:
            log.debug(f"   {speler} geselecteerd (data-id={data_id}, zoekterm '{zoekterm}')")
            # Defensief: ruim mystery-toevoegingen op (Daniel â†’ Ellen Daniels
            # bug uit run #69). Onverwachte data-ids in #youPlayWith â†’ Ã—-klik.
            _ruim_onverwachte_spelers_op(driver, verwachte_data_ids | {data_id})
            return data_id

        # data-id niet in youPlayWith â†’ speler niet toegevoegd. ABORT.
        log.error(f"   Speler NIET in 'Je gaat spelen met' na 4 verifieer-pogingen "
                  f"— data-id {data_id} niet aanwezig. ETV heeft de selectie "
                  f"geweigerd of de click landde verkeerd.")
        screenshot(driver, f"05d_niet_in_youplaywith_{achternaam}")
        return ""

    log.error(f"   Geen .addPlayer card met exacte match voor '{speler}' "
              f"(geprobeerd: {zoektermen})")
    try:
        zichtbaar_tekst = driver.find_element(By.TAG_NAME, "body").text
        log.error(f"  Paginatekst (500 tekens): {zichtbaar_tekst[:500]}")
    except Exception:
        pass
    screenshot(driver, f"05c_niet_gevonden_{achternaam}")
    return ""


def voeg_spelers_toe(driver: uc.Chrome, speler2: str, speler3: str, speler4: str,
                      is_retry: bool = False) -> bool:
    log.info("Spelers toevoegen...")
    time.sleep(1)

    # Defensieve refresh alleen bij retry (outer_poging > 1): stale state
    # uit een vorige poging opruimen. Eerste run heeft verse sessie.
    if is_retry:
        try:
            driver.refresh()
            try:
                WebDriverWait(driver, 8).until(
                    lambda d: _zoek_veld_spelers(d) is not None
                )
            except TimeoutException:
                time.sleep(1)
            log.info(f"   ReservationsPlayers ververst  URL: {driver.current_url}")
        except Exception as e:
            log.warning(f"  Refresh mislukt ({e}), doorgaan op huidige page state")


    # Log wie er al in #youPlayWith staat (eventueel leftover van een
    # eerder gecrashte booking-poging). Joris staat er altijd in als speler 1.
    try:
        bestaand = driver.execute_script("""
            var c = document.getElementById('youPlayWith');
            if (!c) return [];
            return Array.from(c.querySelectorAll('h6')).map(h => h.innerText.trim());
        """)
        log.debug(f"  Al in 'Je gaat spelen met' bij start: {bestaand}")
    except Exception:
        pass

    # Start cleanup: alles wat bij start in #youPlayWith staat is per definitie
    # onverwacht (we hebben nog niemand toegevoegd). Verwijder leftover state.
    leftover = _ruim_onverwachte_spelers_op(driver, set())
    if leftover:
        log.info(f"   Start-cleanup: {len(leftover)} leftover speler(s) verwijderd: {leftover}")

    # Track data-ids van succesvol toegevoegde spelers. Wordt aan
    # _voeg_speler_toe meegegeven zodat die de Ã— kan klikken bij
    # ELKE andere data-id in #youPlayWith (mystery-spelers uit
    # ETV's typeahead-substring-matches — bug uit run #68/#69).
    toegevoegde_data_ids = set()
    for i, speler in enumerate([speler2, speler3, speler4], start=2):
        log.debug(f"Speler {i} toevoegen: '{speler}'")
        # 2-poging retry. Bij fail (network glitch, ETV typeahead die niet laadt,
        # of een onverwacht ETV-foutgeval): refresh + opnieuw. De defensieve
        # cleanup uit commit ae2bfbd zorgt dat een halve eerdere poging geen
        # state-vervuiling achterlaat — opnieuw beginnen is veilig.
        nieuwe_id = ""
        for spelers_poging in range(1, 3):
            nieuwe_id = _voeg_speler_toe(driver, speler, i, toegevoegde_data_ids)
            if nieuwe_id:
                break
            if spelers_poging < 2:
                log.warning(f"   Speler {i} ('{speler}') faalde op poging {spelers_poging}  "
                            f"refresh + retry...")
                try:
                    driver.refresh()
                    time.sleep(3)
                    # Na refresh: cleanup eventuele stale state opnieuw, en
                    # check welke spelers nog OK in #youPlayWith staan.
                    _ruim_onverwachte_spelers_op(driver, toegevoegde_data_ids)
                except Exception as e:
                    log.warning(f"  Refresh tussen pogingen faalde: {e}")
        if not nieuwe_id:
            log.error(f"   Speler {i} ('{speler}') na 2 pogingen niet toegevoegd  abort")
            return False
        toegevoegde_data_ids.add(nieuwe_id)

    log.info(f"Spelers geselecteerd: {SPELER1}, {speler2}, {speler3}, {speler4}")
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
        log.info(f" Spelers toegevoegd, URL: {driver.current_url}")
        return True
    log.error(" 'Volgende' knop niet gevonden na spelers")
    try:
        log.error(f"Paginatekst: {driver.find_element(By.TAG_NAME,'body').text[:400]}")
    except Exception:
        pass
    screenshot(driver, "volgende_fout_spelers")
    return False


# â"€â"€ STAP 4: Dag en dagdeel kiezen â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
def _vind_daypart(driver, datum: str, gewenst_dagdeel: str):
    """Vind het div.daypart-element voor (datum, dagdeel). Idempotent — re-callable."""
    return driver.execute_script("""
        var targetDate = arguments[0];
        var dagdeel    = arguments[1];
        var candidates = Array.from(document.querySelectorAll('[data-date]'))
            .filter(function(el) {
                var dd = el.getAttribute('data-date') || '';
                return dd.startsWith(targetDate);
            });
        if (!candidates.length) return null;
        for (var i = 0; i < candidates.length; i++) {
            var txt = (candidates[i].innerText || '').trim();
            if (txt === dagdeel || txt.includes(dagdeel)) return candidates[i];
        }
        return null;
    """, datum, gewenst_dagdeel)


def _vind_volgende_knop(driver):
    """Vind de Volgende submit-knop. Idempotent — re-callable na DOM-update."""
    return driver.execute_script("""
        var alle = Array.from(document.querySelectorAll('button, a, [role="button"]'))
            .filter(function(el) {
                return el.offsetParent && (el.innerText || '').trim() === 'Volgende';
            });
        if (!alle.length) return null;
        for (var i = 0; i < alle.length; i++) {
            var cls = (alle[i].className || '').toLowerCase();
            if ((alle[i].getAttribute('type') || '') === 'submit' && cls.includes('next')) return alle[i];
        }
        for (var i = 0; i < alle.length; i++) {
            if ((alle[i].getAttribute('type') || '') === 'submit') return alle[i];
        }
        return alle[alle.length - 1];
    """)


def kies_dag(driver: uc.Chrome, datum: str, tijd: str) -> bool:
    """
    Selecteer dag+dagdeel en navigeer door naar baankeuze.

    Robust retry-pattern: na elke poging wordt de URL gecheckt. Als de server
    ons terug naar ReservationsPlayers stuurt (= dagdeel-selectie geweigerd),
    klikken we daar Volgende om weer naar dag-pagina te komen en proberen het
    opnieuw. Max 3 pogingen.
    """
    log.info(f"Dag kiezen: {datum}, dagdeel: {dagdeel(tijd)}")
    try:
        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script(
                "return document.querySelectorAll('[data-date]').length") > 0
            or "ReservationsCourt" in d.current_url
        )
    except TimeoutException:
        pass  # pagina nog leeg, kies_dag-pogingen vangen dit op
    doel_datum      = datetime.strptime(datum, "%Y-%m-%d")
    dag_nr          = str(doel_datum.day)
    gewenst_dagdeel = dagdeel(tijd)
    log.info(f"Zoek dag={dag_nr}, dagdeel='{gewenst_dagdeel}'")

    # Navigeer naar de juiste week als de dag niet zichtbaar is
    for _ in range(8):
        try:
            if dag_nr in driver.find_element(By.TAG_NAME, "body").text:
                break
        except Exception:
            break
        volgende_week = _zoek_knop(driver, [">"])
        if volgende_week:
            try:
                driver.execute_script("arguments[0].click();", volgende_week)
            except Exception:
                pass
            time.sleep(1.5)
        else:
            break

    try:
        alle_dayparts = driver.execute_script("""
            return Array.from(document.querySelectorAll('[data-date]')).map(function(el) {
                return el.getAttribute('data-date') + ':' + (el.innerText || '').trim().slice(0, 20);
            }).join(' | ');
        """)
        log.debug(f"Alle data-date elementen: {alle_dayparts}")
    except Exception:
        pass

    # â"€â"€ Retry-loop: max 3 pogingen â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    for poging in range(1, 4):
        log.info(f" kies_dag poging {poging}/3 ")

        # Recover: als we op spelers-pagina staan, navigeer direct naar dag-pagina
        url_nu = driver.current_url
        if "ReservationsPlayers" in url_nu:
            log.info("  Op ReservationsPlayers — directe GET naar ReservationsDay")
            try:
                driver.get("https://www.etv-volley.nl/me/ReservationsDay")
                WebDriverWait(driver, 5).until(
                    lambda d: "ReservationsDay" in d.current_url
                              or "ReservationsCourt" in d.current_url
                )
                if "ReservationsCourt" in driver.current_url:
                    log.info("  Direct naar baankeuze — dag-selectie was al OK")
                    return True
            except Exception as e:
                log.warning(f"  Recovery naar dag-pagina mislukt: {e}")
                continue

        if "ReservationsDay" not in driver.current_url:
            log.warning(f"  Verkeerde URL voor dag-keuze: {driver.current_url}")
            time.sleep(2)
            continue

        # Re-fetch daypart element (kan stale zijn na vorige poging)
        try:
            daypart_el = _vind_daypart(driver, datum, gewenst_dagdeel)
        except Exception as e:
            log.warning(f"  Daypart find faalde: {e}")
            time.sleep(2)
            continue

        if not daypart_el:
            log.error(f"  div.daypart voor {datum} / {gewenst_dagdeel} niet gevonden")
            time.sleep(2)
            continue

        try:
            data_date = driver.execute_script("return arguments[0].getAttribute('data-date');", daypart_el)
            log.info(f"  Daypart gevonden: data-date={data_date}")
        except Exception:
            log.warning("  Daypart ref werd stale tijdens read  retry")
            continue

        # â"€â"€ Klik daypart via ActionChains (isTrusted=true) â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        # ETV's jQuery-handlers filteren synthetische events (isTrusted=false) weg.
        # Zonder echte muis-click registreert de server de selectie niet en stuurt
        # je terug naar de spelers-pagina. Zelfde patroon als spelers-fix 29e25f5.
        klik_ok = False
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", daypart_el)
            time.sleep(0.15)
            ActionChains(driver).move_to_element(daypart_el).click().perform()
            log.info("  Daypart geklikt via ActionChains")
            klik_ok = True
        except Exception as e:
            log.warning(f"  ActionChains daypart mislukt ({e}), fallback dispatchEvent")
            try:
                driver.execute_script("""
                    var el = arguments[0];
                    var rect = el.getBoundingClientRect();
                    var cx = rect.left + rect.width / 2;
                    var cy = rect.top + rect.height / 2;
                    ['mouseover', 'mousedown', 'mouseup', 'click'].forEach(function(type) {
                        el.dispatchEvent(new MouseEvent(type, {
                            bubbles: true, cancelable: true, view: window,
                            clientX: cx, clientY: cy
                        }));
                    });
                """, daypart_el)
                klik_ok = True
            except Exception as e2:
                log.warning(f"  Ook dispatchEvent faalde: {e2}")

        if not klik_ok:
            time.sleep(1)
            continue
        time.sleep(0.15)

        # Backup: zet hidden selectedDate input voor sites die 'm uit DOM lezen
        try:
            driver.execute_script("""
                var input = document.querySelector('input[name="selectedDate"]');
                if (!input) return;
                var setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(input, arguments[0]);
                input.dispatchEvent(new Event('input',  {bubbles: true}));
                input.dispatchEvent(new Event('change', {bubbles: true}));
            """, data_date)
        except Exception:
            pass


        # â"€â"€ Volgende-knop opnieuw fetchen (kan na DOM-update stale zijn) â"€â"€â"€â"€
        try:
            volgende = _vind_volgende_knop(driver)
        except Exception as e:
            log.warning(f"  Volgende-knop find faalde: {e}")
            continue

        if not volgende:
            log.warning(f"  Geen Volgende-knop gevonden (poging {poging})")
            time.sleep(2)
            continue

        # â"€â"€ Submit Volgende + wacht op outcome (max 15s) â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        try:
            methode = _submit_knop(driver, volgende)
            log.info(f"  Volgende methode: {methode}")
        except Exception as e:
            log.warning(f"  Volgende submit faalde ({e})")
            time.sleep(2)
            continue

        try:
            WebDriverWait(driver, 1.0, poll_frequency=0.1).until(
                lambda d: "ReservationsCourt" in d.current_url
                          or "ReservationsPlayers" in d.current_url
                          or "ReservationsDay" not in d.current_url
            )
        except TimeoutException:
            log.warning("  Geen herkenbare navigatie binnen 1.0s")
        except Exception:
            pass

        url_na = driver.current_url
        try:
            body_na = driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            body_na = ""

        # â"€â"€ Beoordeel uitkomst â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        if "ReservationsCourt" in url_na:
            log.info(f" Op baankeuze: {url_na}")
            return True

        if ":00" in body_na or ":30" in body_na:
            log.info(f" Tijdsloten zichtbaar (AJAX wizard, URL: {url_na})")
            return True

        # Diagnose: onderscheid ETV-eigen weigering van Cloudflare/WAF-interventie
        # (run #174/#178 lieten kies_dag tot 3+ min falen zonder duidelijkheid
        # waarom -- dit legt bewijsmateriaal vast i.p.v. te gokken).
        try:
            titel_na = driver.title or ""
        except Exception:
            titel_na = ""
        bot_markers = ["cloudflare", "attention required", "checking your browser",
                       "just a moment", "access denied", "rate limit", "too many requests"]
        tekst_check = (titel_na + " " + body_na).lower()
        gedetecteerd = [m for m in bot_markers if m in tekst_check]
        if gedetecteerd:
            log.warning(f"  Mogelijke bot-detectie/rate-limiting gesignaleerd: {gedetecteerd} "
                        f"| titel='{titel_na}' | body[:200]='{body_na[:200]}'")
        else:
            # INFO (niet debug): logging.basicConfig staat op INFO, en dit is
            # juist het bewijsmateriaal dat we nodig hebben als de gok-lijst
            # met bot-markers de ETV/Cloudflare-bewoording mist.
            log.info(f"  Diagnose Volgende-mislukking | titel='{titel_na}' | body[:200]='{body_na[:200]}'")

        if "ReservationsPlayers" in url_na:
            log.warning(f"   Server stuurde terug naar spelers  daypart selectie geweigerd. "
                        f"Retry (poging {poging+1}/3)")
            time.sleep(1)
            continue

        # Nog steeds ReservationsDay — ETV heeft submit niet verwerkt.
        # Geen refresh (wist dagpart-selectie); direct opnieuw proberen.
        log.info(f"  Geen navigatie na Volgende — blijft op {url_na}")

    log.error(f" kies_dag faalde definitief na 3 pogingen")
    return False


# â"€â"€ STAP 5: Baan en tijd kiezen â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
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
                        log.info(f" Cookie-banner gesloten via '{el.text.strip()[:30]}'")
                        time.sleep(0.8)
                        return
            except Exception:
                pass
    finally:
        driver.implicitly_wait(5)


def kies_baan_en_tijd(driver: uc.Chrome, voorkeur_tijd: str, sport: str = "padel") -> tuple:
    """
    Kies een padelbaan + tijdslot.

    Doorloop-volgorde: voor elke kandidaat-tijd (voorkeur eerst, dan alternatieven)
    pakt de JS-loop alle tijdcellen met die tijd uit de DOM en kiest degene die
    Y-dichtstbij een Padel-label staat. ETV toont bezette tijdcellen niet op de
    pagina, dus na een verse load is een door iemand anders zojuist geboekte
    baan automatisch verdwenen — geen expliciete uitsluit-lijst nodig.
    """
    log.info("Baankeuze pagina laden...")

    # Wacht tot de tijdslot-pagina geladen is
    try:
        WebDriverWait(driver, 30).until(
            lambda d: ":00" in d.find_element(By.TAG_NAME, "body").text
                      or ":30" in d.find_element(By.TAG_NAME, "body").text
        )
        log.info(" Tijdslot-pagina geladen (tijden zichtbaar)")
    except TimeoutException:
        try:
            log.warning(f" Tijdslot-pagina niet geladen na 30s  bodytekst: "
                        f"{driver.find_element(By.TAG_NAME,'body').text[:500]}")
        except Exception:
            log.warning(" Tijdslot-pagina niet geladen na 30s  body niet leesbaar")

    time.sleep(1)

    # â"€â"€ Sluit cookie-banner vÃ³Ã³r we iets klikken â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    _sluit_cookie_banner(driver)

    tijden = genereer_tijden(voorkeur_tijd)
    log.info(f"Tijden om te proberen: {tijden}")

    # Log paginatekst voor diagnose
    try:
        pagina = driver.find_element(By.TAG_NAME, "body").text
        log.debug(f"Baan-pagina tekst (3000): {pagina[:3000]}")
    except Exception:
        pass

    # â"€â"€ Scroll naar padel-rijen zodat getBoundingClientRect() klopt â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    # Padel-banen staan onderaan het grid; scroll ze eerst in beeld zodat de
    # browser hun layout berekend heeft en de Y-coÃ¶rdinaten kloppen.
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
        """, PADEL_BANEN if sport == "padel" else TENNIS_BANEN)
        log.debug(f"Scroll naar {sport}: {scroll_result}")
        time.sleep(0.8)
        _sluit_cookie_banner(driver)
    except Exception as e:
        log.warning(f"Scroll naar padel mislukt: {e}")

    for tijd in tijden:
        log.info(f"Zoek {sport} tijdslot '{tijd}'...")

        # Zoek tijdslot in een padel-rij via ABSOLUTE document-Y (scroll-onafhankelijk).
        # getBoundingClientRect().top + window.scrollY = absolute document-Y.
        # DOM-structuur based matching (sinds run #75 + ETV-HTML-inzicht 01-06):
        # Het ETV-grid is een accordion met <div class="court"> per baan. Elke
        # court heeft:
        #   - <button class="btn-link"> met text "9 Padel 1<span>Padel</span>"
        #   - <div data-hour="N" class="timeincourt"> per uur; class="disabled"
        #     als niet boekbaar. <option>-elementen binnen het <select> per
        #     boekbaar 5-min-slot.
        #
        # Strategie:
        #   1. Loop over .court containers, filter op padel-banen via button-tekst
        #   2. Per padel-court: vind .timeincourt:not(.disabled) waarvan
        #      innerText met de gewenste tijd start (bv. "18:30" of "15:00")
        #   3. Eerste match wint (laagste Padel-nummer eerst)
        #
        # Voordelen vs. de oude Y-coÃ¶rdinaat-aanpak:
        #   - Geen cross-rij mismatches (run #75 koos Padel 1 voor 18:00 want
        #     een tennis/pickle-cel was 53px van Padel 1's label)
        #   - .disabled cellen worden expliciet uitgesloten
        #   - Werkt onafhankelijk van accordion-expand-state / scrollpositie
        result = driver.execute_script("""
            var tijd  = arguments[0];
            var sport = arguments[1];
            var found = null;
            document.querySelectorAll('.court').forEach(function(court) {
                if (found) return;
                var btn = court.querySelector('button.btn-link');
                if (!btn) return;
                var courtNaam = (btn.innerText || '').trim();
                var baanLabel;
                if (sport === 'tennis') {
                    if (courtNaam.indexOf('Smashcourt') < 0) return;
                    var nm = courtNaam.match(/\b(\d{2})\b/);
                    baanLabel = nm ? 'Tennis ' + nm[1] : 'Tennis';
                } else {
                    var m = courtNaam.match(/Padel \d/);
                    if (!m) return;
                    baanLabel = m[0];
                }
                var cellen = court.querySelectorAll('.timeincourt:not(.disabled)');
                for (var i = 0; i < cellen.length; i++) {
                    var cel = cellen[i];
                    var txt = (cel.innerText || '').trim();
                    if (txt === tijd || txt.startsWith(tijd)) {
                        found = { cel: cel, baan: baanLabel };
                        return;
                    }
                }
            });
            window._kiesBaanResult = found ? found.baan : 'geen';
            return found;
        """, tijd, sport)

        try:
            d_resultaat = driver.execute_script('return window._kiesBaanResult || ""')
            log.debug(f"  diagnose: match='{d_resultaat}' voor tijd '{tijd}'")
        except Exception:
            pass

        if not result:
            log.info(f"  Geen {sport} tijdslot '{tijd}' gevonden (bezet of buiten drempel)")
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
            log.debug(f"  Tijdslot element: {info}")
        except Exception:
            pass

        time.sleep(0.15)
        # NIET _sluit_cookie_banner() aanroepen hier: de cookie-banner is al gesloten
        # en find_elements() wacht met implicit_wait=5s per XPATH = 25s voor niets.

        # â"€â"€ Klik via ActionChains (real mouse event, NIET JS click) â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        try:
            ActionChains(driver).move_to_element(cel).click().perform()
            log.info(f"   ActionChains klik op {tijd}, baan={baan}")
        except Exception as e:
            log.warning(f"  ActionChains mislukt ({e}), fallback JS click")
            try:
                driver.execute_script("arguments[0].click();", cel)
                log.info(f"  JS click als fallback uitgevoerd")
            except Exception as e2:
                log.warning(f"  JS click ook mislukt: {e2}")

        # Kort: dit valt binnen het kies->bevestig race-venster met andere
        # boekers (zie README "Race-conditie afhandeling") -- elke ms hier
        # is direct concurrentienadeel. DOM-classwissel na klik is synchroon
        # client-side JS, geen serverroundtrip nodig.
        time.sleep(0.3)

        # â"€â"€ Controleer of de selectie geregistreerd is â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
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
        fout_tekst = selectie_ok.get('fout', '')
        log.info(f"  Selectiestatus: cls='{selectie_ok.get('cls','')}' "
                 f"selected={selectie_ok.get('selected',False)} "
                 f"fout='{fout_tekst}'")

        if fout_tekst:
            log.warning(f"  Foutmelding na klik op {tijd}: '{fout_tekst}' — volgende tijdslot")
            continue

        try:
            body_na = driver.find_element(By.TAG_NAME, "body").text
            log.debug(f"  Body na klik (500): {body_na[:500]}")
        except Exception:
            pass

        log.info(f" Tijdslot {tijd} geselecteerd, baan={baan}")
        return baan, tijd

    log.error(f" Geen beschikbaar {sport} tijdslot gevonden!")
    screenshot(driver, "baan_fout")
    return "", ""


# â"€â"€ STAP 6: Bevestigen â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
def _submit_knop(driver: uc.Chrome, knop) -> str:
    """Dien een form in via requestSubmit â†’ form.submit() â†’ ActionChains â†’ JS click."""
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


def bevestig(driver: uc.Chrome, dry_run: bool = False) -> str:
    """
    Stap 6: klik Volgende â†’ ga naar bevestigingspagina â†’ klik 'Bevestigen'.

    Returnt een string-code:
      'OK'    — reservering succesvol gemaakt (of bij dry_run=True: simulatie OK)
      'BEZET' — server zegt 'niet gevonden' (baan werd net door iemand anders
                geboekt, of vergelijkbare race-conditie) — main() kan terug
                naar baan-keuze en een andere baan proberen
      'FOUT'  — andere fout, geen retry mogelijk

    dry_run=True: Loopt door alle stappen behalve de Bevestig-knop-klik.
                  Logt ðŸ§ª DRY-RUN-merker, maakt een screenshot 'dry_run_zou_klikken'
                  en returnt 'OK'. Bedoeld voor end-to-end-testen zonder echte
                  reservering bij ETV.

    De bevestigingsknop is een <a id="confirmReservationButton"
    data-url="/Ajax/Profile/SaveReservation" data-redirect="/me/Reservations">.
    Geen form — de knop triggert een AJAX-call via een jQuery click-handler.
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
        # â"€â"€ Stap 1: Volgende â†’ bevestigingspagina â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
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
            time.sleep(0.3)
            url_na_vol = driver.current_url
            log.info(f"  URL na Volgende: {url_na_vol}")
            try:
                log.debug(f"  Body na Volgende (400): "
                          f"{driver.find_element(By.TAG_NAME,'body').text[:400]}")
            except Exception:
                pass

            # Controleer of we op de juiste pagina zijn (ReservationsConfirm)
            if "ReservationsConfirm" not in url_na_vol:
                log.error(f" Volgende bracht ons naar {url_na_vol} i.p.v. ReservationsConfirm "
                          f"— court-selectie mogelijk niet geregistreerd")
                screenshot(driver, "bevestig_fout_verkeerde_pagina")
                return 'FOUT'

        # â"€â"€ Stap 2: zoek confirmReservationButton (op id of data-url) â"€â"€â"€â"€â"€â"€â"€
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
            log.error(" confirmReservationButton niet gevonden via id/data-url")
            try:
                log.error(f"Paginatekst: {driver.find_element(By.TAG_NAME,'body').text[:600]}")
            except Exception:
                pass
            screenshot(driver, "bevestig_fout")
            return 'FOUT'

        log.info(f"  Knop gevonden: id={knop_info.get('id')} "
                 f"data-url={knop_info.get('dataUrl')} "
                 f"redirect={knop_info.get('redirect')}")
        log.debug(f"  HTML: {knop_info.get('html')}")

        data_url = knop_info.get('dataUrl', '')
        redirect = knop_info.get('redirect', '/me/Reservations')

        if not data_url:
            log.error(" data-url attribuut ontbreekt op bevestig-knop")
            screenshot(driver, "bevestig_fout")
            return 'FOUT'

        # â"€â"€ DRY-RUN: stop hier, ga niet daadwerkelijk reserveren â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
        if dry_run:
            log.info(" DRY-RUN: Bevestig-knop gevonden en klaar voor klik  STOP HIER")
            log.info(f" Zou clicken: id={knop_info.get('id')} data-url={data_url}")
            screenshot(driver, "dry_run_zou_klikken")
            log.info(" Geen echte reservering gemaakt. Returnt 'OK' (simulatie geslaagd).")
            return 'OK'

        # â"€â"€ Stap 3A: Intercept jQuery handler â†’ haal POST-params op â"€â"€â"€â"€â"€â"€â"€â"€â"€
        # De site's jQuery click-handler op de bevestig-knop stuurt de reservering-
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
        try:
            WebDriverWait(driver, 5).until(
                lambda d: d.execute_script("return !!window._interceptedCalled;")
            )
        except TimeoutException:
            pass
        time.sleep(0.2)

        # Lees de onderschepte POST-data en AJAX-respons
        intercepted_data  = driver.execute_script("return window._interceptedData;")
        intercepted_called = driver.execute_script("return window._interceptedCalled;")
        ajax_response     = driver.execute_script("return window._ajaxResponse;")
        ajax_status       = driver.execute_script("return window._ajaxStatus;")
        log.info(f"  Onderschept: called={intercepted_called} data={intercepted_data}")
        log.info(f"  AJAX response: status={ajax_status} body={ajax_response}")

        # Controleer op server-side fout: "Niet gevonden" = baan was net door
        # iemand anders geboekt (race), of equivalente afwijzing
        if ajax_response and (
            "niet gevonden" in ajax_response.lower()
            or "not found" in ajax_response.lower()
            or "al gereserveerd" in ajax_response.lower()
            or "reeds geboekt" in ajax_response.lower()
            or "niet meer beschikbaar" in ajax_response.lower()
        ):
            log.warning(f"   Server wees reservering af (Poging A): '{ajax_response}'  "
                        f"vermoedelijk net door iemand anders gereserveerd")
            return 'BEZET'

        # Wacht op redirect (kan al gebeurd zijn via de site's eigen success-callback)
        if _wacht_op_redirect(12):
            url_na = driver.current_url
            try:
                body_a = driver.find_element(By.TAG_NAME, "body").text
                log.info(f"  Body na bevestiging A (600): {body_a[:600]}")
            except Exception:
                pass
            log.info(f" Bevestigd via jQuery-trigger! Redirect naar {url_na}")
            screenshot(driver, "12_na_bevestiging")
            return 'OK'

        url_na = driver.current_url
        log.warning(f"  Poging A geen redirect  URL: {url_na}")

        # â"€â"€ Stap 3B: jQuery.ajax() met onderschepte params (of leeg) â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
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
                        bodyLower.indexOf('not found') >= 0 ||
                        bodyLower.indexOf('actieve boekingen') >= 0 ||
                        bodyLower.indexOf('actieve reservering') >= 0 ||
                        bodyLower.indexOf('kan niet worden') >= 0) {
                        window._bevestigStatus = 'error:etv-limiet';
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

            # Controleer of Poging B ook 'baan bezet' terugkreeg
            if b_status == 'error:not-found' or (
                b_fout and (
                    "niet gevonden" in b_fout.lower()
                    or "not found" in b_fout.lower()
                    or "al gereserveerd" in b_fout.lower()
                    or "reeds geboekt" in b_fout.lower()
                    or "niet meer beschikbaar" in b_fout.lower()
                )
            ):
                log.warning(f"   Server wees reservering ook af (Poging B): "
                            f"'{b_fout or b_resp}' — vermoedelijk baan bezet")
                return 'BEZET'

            if b_status == 'error:etv-limiet':
                global _boek_etv_reden
                _boek_etv_reden = (b_resp or b_fout or "ETV weigerde reservering")[:200]
                log.error(f" ETV-limiet/fout in bevestig body: '{_boek_etv_reden}'")
                screenshot(driver, "bevestig_etv_limiet")
                return 'FOUT'
            log.info(f" Bevestigd via jQuery.ajax+data! Redirect naar {url_na2}")
            screenshot(driver, "12_na_bevestiging")
            return 'OK'

        fout   = driver.execute_script("return window._bevestigFout || '(geen fout)';")
        status = driver.execute_script("return window._bevestigStatus || '(onbekend)';")
        url_na2 = driver.current_url
        try:
            body_na2 = driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            body_na2 = ""
        log.error(f" Bevestigen definitief mislukt  "
                  f"status={status} fout={fout} url={url_na2}")
        log.error(f"   Body: {body_na2[:400]}")
        screenshot(driver, "bevestig_fout")
        return 'FOUT'

    except Exception as e:
        log.error(f" Bevestigen mislukt (exception): {e}")
        screenshot(driver, "bevestig_fout")
        return 'FOUT'


# â"€â"€ STAP 7: Verificatie â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
def verifieer_reservering(driver: uc.Chrome, datum: str, tijd: str) -> str:
    """
    Controleer of de reservering zichtbaar is op de reserveringspagina.
    Probeert zowel /mijn/Reservations als /me/Reservations.
    Geeft de naam van de gereserveerde baan terug (bijv. 'Padel 1'), of '' als niet gevonden.
    """
    log.info("Reservering verifiren...")

    _NL_MAANDEN = ["", "januari", "februari", "maart", "april", "mei", "juni",
                   "juli", "augustus", "september", "oktober", "november", "december"]
    datum_obj  = datetime.strptime(datum, "%Y-%m-%d")
    datum_nl   = f"{datum_obj.day}-{datum_obj.month}"                           # bijv. "17-6"
    datum_nl2  = f"{datum_obj.day} {_NL_MAANDEN[datum_obj.month]}"             # bijv. "17 juni"
    datum_nl3  = f"{datum_obj.day:02d}-{datum_obj.month:02d}-{datum_obj.year}" # "17-06-2026"
    # Let op: gebruik GEEN losse tijdstring als zoekterm — die matcht ook op reserveringen
    # van andere datums (bijv. een bestaande reservering op een andere dag om 15:00).
    # Vereiste: datum Ã‰N tijd moeten allebei aanwezig zijn op de pagina.
    datum_tekens = [datum, datum_nl, datum_nl2, datum_nl3]

    def _check_pagina(url: str, scherm_naam: str) -> str:
        try:
            driver.get(url)
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: len((d.find_element(By.TAG_NAME, "body").text or "")) > 50
                )
            except TimeoutException:
                pass
            screenshot(driver, scherm_naam)
            body = driver.find_element(By.TAG_NAME, "body").text
            log.info(f"  {url} body (800): {body[:800]}")

            # Verificatie: datum Ã©n tijd moeten allebei aanwezig zijn
            datum_ok = any(t in body for t in datum_tekens)
            tijd_ok  = tijd in body
            if datum_ok and tijd_ok:
                baan_naam = next((b for b in PADEL_BANEN if b in body), "")
                log.info(f" Reservering BEVESTIGD op {url}! baan={baan_naam or '(onbekend)'}")
                return baan_naam or "Padel"

            log.info(f"  Reservering NIET gevonden op {url} "
                     f"(datum_ok={datum_ok} tijd_ok={tijd_ok} "
                     f"datum_tekens={datum_tekens} tijd='{tijd}')")
            return ""
        except Exception as e:
            log.warning(f"  Verificatie fout op {url}: {e}")
            return ""

    # Probeer eerst /mijn/Reservations (Mijn Reserveringen-overzicht)
    baan = _check_pagina("https://www.etv-volley.nl/mijn/Reservations",
                         "13_mijn_reserveringen")
    if baan:
        return baan

    # Probeer /me/Reservations (wizard-startpagina, toont ook huidige reservering)
    baan = _check_pagina("https://www.etv-volley.nl/me/Reservations",
                         "13b_me_reserveringen")
    if baan:
        return baan

    log.error(f" Reservering NIET zichtbaar op beide reserveringspagina's!")
    log.error(f"   Gezocht op: {datum_tekens}")
    return ""


# â"€â"€ Main â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
def _zet_in_wachtrij(datum: str, tijd: str, speler2: str, speler3: str, speler4: str, sport: str = "padel") -> bool:
    """
    Schrijf een wachtrij-bestand voor latere verwerking en push naar de repo.
    Wordt gebruikt als de speeldatum nog meer dan 2 dagen weg ligt — de
    verwerk_wachtrij.yml workflow pikt het bestand op om 07:00 NL op de reserveringsdatum
    en triggert boek.yml opnieuw met deze inputs.
    """
    import subprocess
    tijd_slug = tijd.replace(":", "")
    bestand = f"wachtrij/{GEBRUIKER}/{datum}_{tijd_slug}.json"
    payload = {
        "gebruiker": GEBRUIKER,
        "datum":     datum,
        "tijd":      tijd,
        "sport":     sport,
        "spelers":   [SPELER1, speler2, speler3, speler4],
        "ingediend": _nu_nl().isoformat(timespec="seconds"),
    }
    map_pad = f"wachtrij/{GEBRUIKER}"
    os.makedirs(map_pad, exist_ok=True)
    gitkeep = f"{map_pad}/.gitkeep"
    if not os.path.exists(gitkeep):
        open(gitkeep, "w").close()
    with open(bestand, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    log.info(f" Wachtrij-bestand geschreven: {bestand}")

    try:
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "config", "user.name",  "knltb-autoboek-bot"], check=True)
        subprocess.run(["git", "add", gitkeep, bestand], check=True)
        subprocess.run(["git", "commit", "-m", f"wachtrij: voeg {datum} om {tijd} toe"], check=True)
    except subprocess.CalledProcessError as e:
        log.error(f" Git commit voor wachtrij mislukt: {e}")
        return False

    # Unshallow indien nodig (actions/checkout doet standaard fetch-depth=1).
    subprocess.run(["git", "fetch", "--unshallow", "origin"], capture_output=True)

    # Retry-lus voor race condities met andere bots/commits op main.
    # --autostash: stash unstaged wijzigingen automatisch voor de rebase
    # zodat dirty working tree geen blokkade vormt.
    for poging in range(1, 6):
        r = subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            subprocess.run(["git", "rebase", "--abort"], capture_output=True)
            log.warning(f"  git pull --rebase mislukt (poging {poging}): {r.stderr.strip()[:300]} — retry")
            time.sleep(poging)
            continue
        push = subprocess.run(["git", "push", "origin", "HEAD:main"],
                              capture_output=True, text=True)
        if push.returncode == 0:
            log.info(f" Wachtrij-bestand gecommit en gepusht (poging {poging})")
            return True
        log.warning(f"  Push poging {poging} mislukt: {push.stderr.strip()[:200]} — retry na {poging}s")
        time.sleep(poging)
    log.error(" Push voor wachtrij faalde na 5 pogingen")
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--datum",   required=True)
    parser.add_argument("--tijd",    required=True)
    parser.add_argument("--speler2", required=True)
    parser.add_argument("--speler3", required=True)
    parser.add_argument("--speler4", required=True)
    parser.add_argument("--sport",   default="padel", choices=["padel", "tennis"])
    parser.add_argument("--dry-run", action="store_true",
                        help="Loop alle stappen door behalve de Bevestig-knop-klik. "
                             "End-to-end test zonder echte reservering bij ETV.")
    args = parser.parse_args()
    if args.dry_run:
        log.info("=" * 50)
        log.info(" DRY-RUN MODE  er wordt GEEN echte reservering gemaakt.")
        log.info("=" * 50)

    if not BONDSNUMMER or not WACHTWOORD:
        log.error(" Stel ETVVOLLEY_BONDSNUMMER en ETVVOLLEY_WACHTWOORD in als GitHub Secrets!")
        _schrijf_boekstatus("fout", "Inloggegevens ontbreken")
        sys.exit(1)

    try:
        speeldatum = datetime.strptime(args.datum, "%Y-%m-%d")
    except ValueError:
        log.error(" Datum moet YYYY-MM-DD zijn")
        _schrijf_boekstatus("fout", "Ongeldige datum opgegeven")
        sys.exit(1)

    # Reserveringsstrategie: vanaf 07:00 op (speeldatum - 2 kalenderdagen) mag worden gereserveerd.
    # Dat geldt voor alle dagdelen van dag 0, dag+1 en dag+2.
    nu            = _nu_nl()
    reserveringsdatum = speeldatum - timedelta(days=2)
    dag_verschil  = (speeldatum.date() - nu.date()).days
    log.info(f" Speeldatum dag+{dag_verschil} | reserveringsdatum: {reserveringsdatum.strftime('%d-%m-%Y')} om 07:00")

    if nu.date() < reserveringsdatum.date():
        log.info(f" Te vroeg om direct te reserveren  speeldatum is over {dag_verschil} dagen. "
                 f"Reserveringsdatum: {reserveringsdatum.strftime('%d-%m-%Y')} om 07:00 NL.")
        log.info(" Zet in wachtrij voor automatische reservering op de reserveringsdatum.")
        if _zet_in_wachtrij(args.datum, args.tijd, args.speler2, args.speler3, args.speler4, args.sport):
            log.info(f" In wachtrij gezet  verwerk_wachtrij workflow start de reservering "
                     f"automatisch op {reserveringsdatum.strftime('%d-%m-%Y')} om 07:00 NL.")
            _schrijf_boekstatus("wachtrij",
                                f"In wachtrij — reservering start automatisch op {reserveringsdatum.strftime('%d-%m-%Y')} om 07:00",
                                datum=args.datum, tijd=args.tijd, sport=args.sport,
                                spelers=[SPELER1, args.speler2, args.speler3, args.speler4])
            github_output = os.environ.get("GITHUB_OUTPUT", "")
            if github_output:
                with open(github_output, "a") as f:
                    f.write("boek_resultaat=wachtrij\n")
            sys.exit(0)
        log.error(" Kon wachtrij-bestand niet opslaan  reservering NIET ingepland")
        _schrijf_boekstatus("fout", "Wachtrij-bestand kon niet worden opgeslagen",
                            datum=args.datum, tijd=args.tijd, sport=args.sport,
                            spelers=[SPELER1, args.speler2, args.speler3, args.speler4])
        sys.exit(1)
    else:
        log.info(f" Reserveren! (dag+{dag_verschil}, reserveringsdatum bereikt)")
        if nu.date() == reserveringsdatum.date() and (nu.hour < 7 or (nu.hour == 7 and nu.minute < 1)):
            log.info("   Cron is vroeg gestart — login/spelers worden NU al voorbereid, "
                     "dag-selectie start om 07:00:10 NL.")

    log.info("=" * 50)
    log.info(" ETV Volley Baan Auto-Reservering")
    log.info(f"   Datum:   {args.datum}")
    log.info(f"   Tijd:    {args.tijd}")
    log.info(f"   Spelers: {SPELER1}, {args.speler2}, {args.speler3}, {args.speler4}")
    log.info("=" * 50)

    baan, gereserveerde_tijd = "", ""
    driver = None

    try:
        driver = maak_driver()
        # Login met onderhoud-retry: bij ETV-onderhoudspagina max 5Ã—
        # wachten (3 min per poging) voor we opgeven.
        MAX_LOGIN_POGINGEN = 5
        ONDERHOUD_WACHT_SEC = 180
        for login_poging in range(1, MAX_LOGIN_POGINGEN + 1):
            login_result = login(driver)
            if login_result is True:
                break
            if login_result == 'ONDERHOUD':
                if login_poging < MAX_LOGIN_POGINGEN:
                    log.warning(f" ETV in onderhoud  wacht {ONDERHOUD_WACHT_SEC}s en probeer opnieuw "
                                f"(poging {login_poging}/{MAX_LOGIN_POGINGEN})")
                    time.sleep(ONDERHOUD_WACHT_SEC)
                    driver.get(LOGIN_URL)
                    time.sleep(4)
                    continue
                log.error(" ETV bleef in onderhoud na alle login-pogingen")
                _schrijf_boekstatus("fout", "ETV Volley is in onderhoud — alle inlogpogingen mislukt",
                                    datum=args.datum, tijd=args.tijd, sport=args.sport,
                                    spelers=[SPELER1, args.speler2, args.speler3, args.speler4])
                sys.exit(1)
            else:
                log.error(" Inloggen mislukt  controleer ETVVOLLEY_BONDSNUMMER en ETVVOLLEY_WACHTWOORD")
                _schrijf_boekstatus("fout", "Inloggen mislukt — controleer bondsnummer en wachtwoord",
                                    datum=args.datum, tijd=args.tijd, sport=args.sport,
                                    spelers=[SPELER1, args.speler2, args.speler3, args.speler4])
                sys.exit(1)

        alle_spelers = [SPELER1, args.speler2, args.speler3, args.speler4]

        # â•"â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
        # â•‘ OUTER-RETRY: volledige wizard-restart bij ETV-restricties        â•‘
        # â•‘                                                                  â•‘
        # â•‘ Achtergrond (run #74, 01-06): ETV gaf na Volgende-klik op de     â•‘
        # â•‘ dag-keuze geen navigatie terug. Doeldatum (03-06, dag+2) bleek   â•‘
        # â•‘ op die pagina als 'grijs/disabled' getoond — vermoedelijk omdat  â•‘
        # â•‘ er al een actieve reservering bestond ('1 actieve reservering'  â•‘
        # â•‘ vermoeden uit valkuil 11.9) of omdat ETV de dag+2-slot op een    â•‘
        # â•‘ tragere cadens vrijgeeft dan precies 07:00.                      â•‘
        # â•‘                                                                  â•‘
        # â•‘ Joris-wens: bij faal in kies_dag (of bevestig met 'FOUT')        â•‘
        # â•‘ volledig herstart vanaf 'Baan afhangen' (spelers opnieuw, etc.). â•‘
        # â•‘ Max 5 pogingen met 30s wachten tussendoor zodat ETV server-side  â•‘
        # â•‘ state-changes mee kan pakken.                                    â•‘
        # â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        MAX_OUTER_POGINGEN = 5
        boek_gelukt = False
        baan = ""
        gereserveerde_tijd = ""
        spelers_gedaan = False

        for outer_poging in range(1, MAX_OUTER_POGINGEN + 1):
            log.info(f" BOEK-POGING {outer_poging}/{MAX_OUTER_POGINGEN} ")

            if outer_poging > 1:
                if spelers_gedaan:
                    # Alleen dag-selectie moet over  geen 30s-page-reload-buffer nodig,
                    # spelers staan al vast en er is geen wizard-restart gebeurd.
                    log.info(" Spelers al succesvol ingevoerd — navigeer direct naar dag-pagina.")
                    try:
                        driver.get("https://www.etv-volley.nl/me/ReservationsDay")
                        time.sleep(1)
                        if "ReservationsDay" not in driver.current_url:
                            log.warning(f" ETV stuurde door naar {driver.current_url} — volledige herstart.")
                            spelers_gedaan = False
                    except Exception as e:
                        log.warning(f"Navigatie naar dag-pagina mislukt: {e} — volledige herstart.")
                        spelers_gedaan = False

                if not spelers_gedaan:
                    # Wel een volledige wizard-restart nodig (spelers/baan-afhangen faalde)
                    # dat is een minder tijdkritiek pad  hier wél buffer voor ETV server-state.
                    time.sleep(30)
                    log.info(" Herstart wizard vanaf 'Baan afhangen'...")
                    try:
                        driver.get("https://www.etv-volley.nl/me/Reservations")
                        time.sleep(3)
                    except Exception as e:
                        log.warning(f"Terugnavigeren naar /me/Reservations faalde: {e}")

            if not spelers_gedaan:
                if not klik_baan_afhangen(driver):
                    log.error(f" 'Baan afhangen' knop niet gevonden (poging {outer_poging})")
                    continue  # outer retry

                if not voeg_spelers_toe(driver, args.speler2, args.speler3, args.speler4,
                                     is_retry=(outer_poging > 1)):
                    log.error(f" Speler niet gevonden (poging {outer_poging}) — outer-retry")
                    continue  # outer-retry; bij uitputting van alle pogingen faalt de job

                spelers_gedaan = True
                _log_zichtbare_spelers(driver, alle_spelers,
                    "na voeg_spelers_toe (4 verwacht)")

            # Dag-selectie: eerste poging zo vroeg mogelijk (07:00:01). Bij mislukking
            # direct opnieuw proberen (0.15s cooldown, geen vaste 10s-slots).
            # Deadline 07:03:00: ETV blijkt de dagdeel-klik pas ~1-2 min na 07:00
            # te accepteren (gezien in run #174-logs) — de binnenlus is goedkoop
            # (~1 pogingen/sec), dus die laten doorlopen is sneller dan escaleren
            # naar de outer-retry (die een dure 30s-wachttijd + herstart kost).
            doel_window_open = reserveringsdatum.replace(hour=7, minute=0, second=1, microsecond=0)
            dag_deadline     = reserveringsdatum.replace(hour=7, minute=3, second=0, microsecond=0)
            MAX_DAG_POGINGEN = 150

            dag_gelukt = False
            for dag_poging in range(1, MAX_DAG_POGINGEN + 1):
                nu = _nu_nl()

                if dag_poging == 1:
                    # Wacht tot 07:00:01; sluit cookie-banner vlak voor het startsein
                    if nu.date() == reserveringsdatum.date() and nu < doel_window_open:
                        wacht_sec = (doel_window_open - nu).total_seconds()
                        log.info(f" Wacht {wacht_sec:.1f}s tot 07:00:01 NL...")
                        if wacht_sec > 5:
                            time.sleep(max(0, wacht_sec - 4))
                            _sluit_cookie_banner(driver)
                            nu2 = _nu_nl()
                            resterend = (doel_window_open - nu2).total_seconds()
                            if resterend > 0:
                                time.sleep(resterend)
                        else:
                            time.sleep(wacht_sec)
                else:
                    # Stop als deadline voorbij (outer-retry pakt het over)
                    if nu.date() == reserveringsdatum.date() and nu > dag_deadline:
                        log.warning(f" Deadline 07:03:00 bereikt na {dag_poging - 1} pogingen — outer-retry.")
                        break
                    time.sleep(0.15)  # korte cooldown tussen pogingen

                if kies_dag(driver, args.datum, args.tijd):
                    dag_gelukt = True
                    log.info(f" Dag-selectie geslaagd op poging {dag_poging}/{MAX_DAG_POGINGEN} om "
                             f"{_nu_nl().strftime('%H:%M:%S')} — direct door naar baankeuze.")
                    break
                log.warning(f" Dag-selectie mislukt (poging {dag_poging}/{MAX_DAG_POGINGEN}) om "
                            f"{_nu_nl().strftime('%H:%M:%S')}")
            if not dag_gelukt:
                log.warning(f" Dag {args.datum} niet selecteerbaar — outer-retry.")
                continue  # outer retry

            _log_zichtbare_spelers(driver, alle_spelers,
                "na kies_dag (baan-grid; spelers mogelijk niet meer zichtbaar)")

            # â"€â"€ Innerlijke retry: baan + tijd kiezen + bevestigen â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
            # Race-conditie: tussen kies_baan_en_tijd en bevestig kan iemand
            # anders nÃ©t sneller zijn. ETV toont bezette tijdcel daarna niet
            # meer; kies_baan_en_tijd pakt automatisch de volgende baan voor
            # dezelfde tijd, dan alternatieve tijden. Max 6 pogingen.
            MAX_BAAN_POGINGEN = 6
            bevestig_ok = False

            for baan_poging in range(1, MAX_BAAN_POGINGEN + 1):
                log.info(f" Baan-poging {baan_poging}/{MAX_BAAN_POGINGEN} ")
                baan, gereserveerde_tijd = kies_baan_en_tijd(driver, args.tijd, args.sport)
                if not baan:
                    log.warning(f" Geen {args.sport}-baan beschikbaar in baan-poging {baan_poging}")
                    break  # naar outer-retry

                _log_zichtbare_spelers(driver, alle_spelers,
                    "na kies_baan_en_tijd (Confirm-pagina; 4 spelers verwacht)")

                resultaat = bevestig(driver, dry_run=args.dry_run)

                if resultaat == 'OK':
                    if args.dry_run:
                        log.info(f" DRY-RUN voltooid op baan-poging {baan_poging}: "
                                 f"{baan} om {gereserveerde_tijd}")
                        log.info(" Geen verdere stappen (verificatie/agenda/reserveringen.json overgeslagen).")
                        sys.exit(0)
                    log.info(f" Bevestigd op baan-poging {baan_poging}: {baan} om {gereserveerde_tijd}")
                    bevestig_ok = True
                    break

                if resultaat == 'BEZET':
                    log.warning(f" {baan} om {gereserveerde_tijd} werd net door iemand anders "
                                f"gereserveerd. Terug naar baan-keuze; bezette slots verdwijnen "
                                f"na de refresh.")
                    try:
                        driver.get("https://www.etv-volley.nl/me/ReservationsCourt")
                        time.sleep(1)
                        log.info(" Forceer expliciete refresh  garandeert verse DOM van ETV")
                        driver.refresh()
                        time.sleep(1)
                    except Exception as e:
                        log.warning(f"Kon niet terug naar baan-keuze: {e}")
                        break  # naar outer-retry
                    continue

                # resultaat == 'FOUT' — outer-retry kan misschien helpen
                log.warning(f" Bevestigen mislukt (FOUT) op baan-poging {baan_poging}  outer-retry.")
                break

            if bevestig_ok:
                boek_gelukt = True
                break  # outer-retry-loop verlaten

            # Hier zonder bevestig_ok: vol of fout â†’ outer-retry
            log.warning(f" Boek-poging {outer_poging} niet gelukt  wacht + restart.")

        if not boek_gelukt:
            log.error(f" Na {MAX_OUTER_POGINGEN} boek-pogingen nog geen reservering gelukt")
            reden = _boek_etv_reden or f"Geen reservering gelukt na {MAX_OUTER_POGINGEN} pogingen"
            _schrijf_boekstatus("fout", reden,
                                datum=args.datum, tijd=args.tijd, sport=args.sport,
                                spelers=[SPELER1, args.speler2, args.speler3, args.speler4])
            sys.exit(1)

        # â"€â"€ Verificeer dat reservering zichtbaar is op Mijn Reserveringen â"€â"€â"€â"€â"€â"€â"€â"€
        geverifieerde_baan = verifieer_reservering(driver, args.datum, gereserveerde_tijd)
        if not geverifieerde_baan:
            # Verificatie mislukt maar reservering is WEL gemaakt (bevestig() returnte 'OK').
            # sys.exit(1) hier zou de cleanup-stap in boek.yml overslaan en het wachtrij-bestand
            # laten staan — waardoor morgen opnieuw geprobeerd wordt te boeken voor dezelfde datum.
            # Daarom: log een warning en ga door zodat de cleanup altijd plaatsvindt.
            log.warning(" Reservering niet zichtbaar op reserveringspagina — verificatie overgeslagen, "
                        "baan-naam onbekend. Agenda wordt NIET bijgewerkt.")
        else:
            # Gebruik geverifieerde baan-naam (betrouwbaarder dan detectie tijdens grid-klik)
            baan = geverifieerde_baan

    finally:
        if driver:
            driver.quit()

    # â"€â"€ Succes: Google Agenda bijwerken â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€
    spelers = [SPELER1, args.speler2, args.speler3, args.speler4]
    datum_nl = speeldatum.strftime("%d-%m-%Y")
    tijdsverschil = f" (voorkeur was {args.tijd})" if gereserveerde_tijd != args.tijd else ""

    log.info("=" * 50)
    log.info(f" GERESERVEERD: {baan} op {datum_nl} om {gereserveerde_tijd}{tijdsverschil}")
    log.info(f"   Spelers: {', '.join(spelers)}")
    log.info("=" * 50)
    tijdsnoot = f" (voorkeur was {args.tijd})" if gereserveerde_tijd != args.tijd else ""
    _schrijf_boekstatus("ok", f"Gereserveerd: {baan} om {gereserveerde_tijd}{tijdsnoot}",
                        datum=args.datum, tijd=gereserveerde_tijd, sport=args.sport,
                        spelers=spelers, baan=baan)

    # Agenda-item wordt aangemaakt in lees_reserveringen.py (beheer_reserveringen.yml)


if __name__ == "__main__":
    main()


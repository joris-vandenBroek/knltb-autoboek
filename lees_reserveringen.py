"""
Beheer actieve ETV-Volley reserveringen:
- Zonder argumenten: scrape /mijn/Reservations en schrijf reserveringen.json
- Met --cancel ID: annuleer de reservering met die ID, dan scrape opnieuw

ID-format: "{YYYY-MM-DD}_{HHMM}_{baan_slug}" zoals "2026-05-31_1500_padel-1"

Strategie:
1. Login via Selenium (UC + Xvfb, bypass Cloudflare) — zelfde patroon als
   haal_leden_op.py en boek_baan.py
2. Navigeer naar /mijn/Reservations
3. Scrape booking rows met heuristieken (tabel-rijen + class-based)
4. (optioneel) Annuleer specifieke reservering
5. Schrijf reserveringen.json + commit/push naar repo
"""

import os
import sys
import json
import time
import argparse
import logging
import re
from datetime import datetime

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

LOGIN_URL        = "https://www.etv-volley.nl/mijn"
RESERVERINGEN_URLS = [
    "https://www.etv-volley.nl/mijn/Reservations",
    "https://www.etv-volley.nl/me/Reservations",
]

BONDSNUMMER         = os.environ.get("KNLTB_BONDSNUMMER", "")
WACHTWOORD          = os.environ.get("KNLTB_WACHTWOORD", "")
GOOGLE_CREDENTIALS  = os.environ.get("GOOGLE_CALENDAR_CREDENTIALS", "")
GOOGLE_CALENDAR_ID  = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
TIMEOUT             = 20


def screenshot(driver, naam: str):
    try:
        driver.save_screenshot(f"{naam}.png")
        log.info(f"📸 Screenshot: {naam}.png | URL: {driver.current_url}")
    except Exception as e:
        log.warning(f"Screenshot mislukt ({naam}): {e}")


def chrome_major_versie():
    import subprocess
    for cmd in [["google-chrome", "--version"], ["google-chrome-stable", "--version"],
                ["chromium-browser", "--version"], ["chromium", "--version"]]:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
            m = re.search(r"(\d+)\.", out)
            if m:
                return int(m.group(1))
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
    """Dunne wrapper rond etv_common.login() — gedeelde flow met
    haal_leden_op.py (en op termijn ook boek_baan.py).
    """
    from etv_common import login as _common_login
    return _common_login(
        driver,
        bondsnummer=BONDSNUMMER,
        wachtwoord=WACHTWOORD,
        login_url=LOGIN_URL,
        screenshot=screenshot,
    )


def maak_id(datum: str, tijd: str, baan: str) -> str:
    """Bouw een stabiele ID uit datum + tijd + baan."""
    tijd_slug = (tijd or "").replace(":", "")
    baan_slug = (baan or "onbekend").lower().replace(" ", "-")
    return f"{datum}_{tijd_slug}_{baan_slug}"


def parse_datum(tekst: str) -> str | None:
    """Vind YYYY-MM-DD of DD-MM-YYYY in tekst. Returnt ISO YYYY-MM-DD."""
    # ISO
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", tekst)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # Nederlands DD-MM-YYYY
    m = re.search(r"(\d{1,2})-(\d{1,2})-(\d{4})", tekst)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    return None


def parse_tijd(tekst: str) -> str | None:
    """Vind HH:MM in tekst."""
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", tekst)
    if m:
        h = int(m.group(1))
        if 0 <= h < 24:
            return f"{h:02d}:{m.group(2)}"
    return None


def parse_baan(tekst: str) -> str | None:
    """Vind 'Padel N' of 'Tennis N' in tekst."""
    m = re.search(r"\b(Padel|Tennis)\s*\d+\b", tekst, re.IGNORECASE)
    if m:
        return m.group(0).title()
    return None


def scrape_reserveringen(driver) -> list:
    """
    Scrape booking-rijen van de reserveringspagina.
    Heuristisch: dump alle plausibele booking-containers, dan extract datum/tijd/baan.
    """
    log.info("Reserveringspagina laden...")

    body_text = ""
    gevonden_url = None
    for url in RESERVERINGEN_URLS:
        try:
            driver.get(url)
            time.sleep(4)
            screenshot(driver, f"03_reserveringen_{url.split('/')[-2]}")
            body_text = driver.find_element(By.TAG_NAME, "body").text
            log.info(f"  {url} body[:500]: {body_text[:500]}")
            # Heeft de pagina herkenbare datum/tijd patronen?
            if re.search(r"\d{1,2}[-/:]\d{1,2}", body_text):
                gevonden_url = url
                break
        except Exception as e:
            log.warning(f"  Kon {url} niet laden: {e}")

    if not gevonden_url:
        log.warning("Geen reservering-tekst gedetecteerd op beide URLs")
        return []

    log.info(f"Reserveringen op: {gevonden_url}")

    # Dump alle plausibele booking-containers met heuristieken
    raw = driver.execute_script("""
        var resultaat = [];

        function veiligTekst(el) {
            return (el.innerText || el.textContent || '').trim();
        }

        // 1) Tabel-rijen
        document.querySelectorAll('table tr').forEach(function(tr) {
            var tds = tr.querySelectorAll('td');
            if (tds.length < 2) return;
            var tekst = veiligTekst(tr);
            if (!tekst || tekst.length < 8 || tekst.length > 800) return;

            // ETV's 'Wijzigen' is een form-submit (POST /me/EditReservation
            // met ReservationId + CSRF token in hidden inputs). De button
            // heeft type="button" en onclick="" — een jQuery-handler op
            // .edit-reservation submit het form. Wij submitten het direct
            // via JS in Python (omzeilt anti-bot/jQuery-bind issues).
            var reservationId = null;
            var editForm = tr.querySelector('form[action*="EditReservation"]');
            if (editForm) {
                var idInput = editForm.querySelector('input[name="ReservationId"]');
                if (idInput) reservationId = idInput.value || null;
            }

            resultaat.push({
                type:          'table-row',
                tekst:         tekst,
                tdCount:       tds.length,
                html:          tr.outerHTML.slice(0, 1200),
                reservationId: reservationId
            });
        });

        // 2) Divs/articles/sections met booking-related class
        var classKeywords = ['booking','reservation','reservering','reservering','my-bookings','my-reservations'];
        document.querySelectorAll('div, article, section, li').forEach(function(el) {
            var cls = (el.className || '').toString().toLowerCase();
            var match = false;
            for (var i = 0; i < classKeywords.length; i++) {
                if (cls.indexOf(classKeywords[i]) >= 0) { match = true; break; }
            }
            if (!match) return;
            var tekst = veiligTekst(el);
            if (!tekst || tekst.length < 8 || tekst.length > 800) return;
            resultaat.push({
                type:    'class-match',
                tekst:   tekst,
                cls:     cls,
                html:    el.outerHTML.slice(0, 800)
            });
        });

        // 3) Cancel/annuleer buttons + hun ancestor-container
        var cancelKeywords = ['annuleer','cancel','verwijder','delete','prullenbak'];
        document.querySelectorAll('button, a, [role="button"]').forEach(function(btn) {
            var t = veiligTekst(btn).toLowerCase();
            var cls = (btn.className || '').toString().toLowerCase();
            var title = (btn.getAttribute('title') || '').toLowerCase();
            var aria = (btn.getAttribute('aria-label') || '').toLowerCase();
            var match = false;
            for (var i = 0; i < cancelKeywords.length; i++) {
                if (t.indexOf(cancelKeywords[i]) >= 0
                    || cls.indexOf(cancelKeywords[i]) >= 0
                    || title.indexOf(cancelKeywords[i]) >= 0
                    || aria.indexOf(cancelKeywords[i]) >= 0) {
                    match = true; break;
                }
            }
            if (!match) return;
            // Geef parent-context
            var parent = btn.closest('tr, li, div[class*="booking"], div[class*="reservation"], div[class*="reservering"]');
            resultaat.push({
                type:    'cancel-button',
                btnTekst: veiligTekst(btn),
                btnCls:  cls,
                btnHtml: btn.outerHTML.slice(0, 400),
                btnHref: btn.getAttribute('href'),
                btnDataUrl: btn.getAttribute('data-url'),
                btnDataId: btn.getAttribute('data-id') || btn.getAttribute('data-reservation-id'),
                parentTekst: parent ? veiligTekst(parent).slice(0, 400) : null,
                parentHtml:  parent ? parent.outerHTML.slice(0, 800) : null
            });
        });

        return resultaat;
    """)

    log.info(f"Rauwe scrape: {len(raw)} kandidaten")
    for r in raw[:20]:
        log.info(f"  [{r.get('type')}] tekst='{r.get('tekst', r.get('btnTekst', ''))[:120]}'")

    # Parse naar gestructureerde reserveringen
    reserveringen = []
    seen_ids = set()

    # Verzamel cancel-buttons met hun parent context
    cancel_buttons = [r for r in raw if r.get('type') == 'cancel-button']

    # Probeer rijen + class-matches te parsen
    voor_parse = [r for r in raw if r.get('type') in ('table-row', 'class-match')]

    for r in voor_parse:
        tekst = r.get('tekst', '')
        datum = parse_datum(tekst)
        tijd  = parse_tijd(tekst)
        baan  = parse_baan(tekst)
        if not (datum and tijd):
            continue
        rid = maak_id(datum, tijd, baan or "onbekend")
        if rid in seen_ids:
            continue
        seen_ids.add(rid)

        # Vind matching cancel-button via parent-tekst match
        cancel_info = None
        for cb in cancel_buttons:
            pt = (cb.get('parentTekst') or '')
            if datum in pt or tijd in pt or (baan and baan in pt):
                cancel_info = {
                    'btnTekst': cb.get('btnTekst'),
                    'btnHref':  cb.get('btnHref'),
                    'btnDataUrl': cb.get('btnDataUrl'),
                    'btnDataId': cb.get('btnDataId'),
                }
                break

        reserveringen.append({
            'id':              rid,
            'datum':           datum,
            'tijd':            tijd,
            'baan':            baan,
            'tekst':           tekst[:300],
            'cancel':          cancel_info,
            '_reservationId':  r.get('reservationId'),  # voor EditReservation POST
            '_trHtml':         r.get('html'),
        })

    log.info(f"Geparseerde reserveringen: {len(reserveringen)}")
    for r in reserveringen:
        log.info(f"  ✓ {r['datum']} {r['tijd']} {r['baan']} (id={r['id']}, cancel={bool(r['cancel'])})")

    return reserveringen


def scrape_spelers_per_reservering(driver, reserveringen: list) -> list:
    """
    Voor elke reservering: navigeer naar de Wijzig-pagina, scrape de
    spelers, navigeer terug. NIET op Bevestig/OK klikken — dat zou ETV
    de reservering opnieuw laten opslaan met mogelijke side-effects.

    Werkwijze:
      1. driver.get(wijzigUrl) — leidt naar ReservationsConfirm of
         vergelijkbare detail-pagina met de bestaande spelers ingevuld
      2. Wacht kort op DOM
      3. Probeer spelers te vinden via:
         a. #youPlayWith li (zelfde structuur als nieuwe-boeking flow)
         b. .player-row, .deelnemer-naam, vergelijkbare class-names
         c. Tabel-rijen met 'speler' / 'partner' label
      4. Sla op in r['spelers'] (lijst van strings, EXCL. de eigenaar Joris)
      5. driver.get(/mijn/Reservations) om terug te keren — schoner dan
         driver.back() (cache-gerelateerde gotchas)

    Bij faal: r['spelers'] blijft leeg/ontbrekend. PWA toont dan
    alleen de baan — graceful degradation, geen crash.
    """
    if not reserveringen:
        return reserveringen
    log.info(f"🔍 Spelers ophalen via Wijzig-flow voor {len(reserveringen)} reservering(en)...")

    for idx, r in enumerate(reserveringen, start=1):
        rid = r.get('id', '?')
        reservation_id = r.get('_reservationId')

        # Vanaf iteratie 2: terug naar overzicht zodat de forms (incl.
        # huidige CSRF tokens) verse referenties zijn voor JS-submit.
        if idx > 1:
            try:
                driver.get("https://www.etv-volley.nl/mijn/Reservations")
                time.sleep(3)
            except Exception as e:
                log.warning(f"  Terugnavigatie naar overzicht faalde: {e}")
                break

        if not reservation_id:
            tr_html_snippet = (r.get('_trHtml') or '')[:600]
            log.info(f"  [{idx}] {rid}: geen ReservationId in tr → skip. tr-HTML (600): {tr_html_snippet}")
            continue

        # Submit het EditReservation-form direct via JS. Werkt rond
        # type="button" + jQuery-event-delegation door form.submit() te
        # forceren met de hidden ReservationId + CSRF-token uit DOM.
        # POST naar /me/EditReservation → server stuurt redirect naar
        # de wijzig-pagina met spelers ingevuld.
        log.info(f"  [{idx}] {rid}: submit EditReservation form (id={reservation_id})")
        try:
            submit_result = driver.execute_script("""
                var rid = arguments[0];
                var forms = document.querySelectorAll('form[action*="EditReservation"]');
                for (var i = 0; i < forms.length; i++) {
                    var input = forms[i].querySelector('input[name="ReservationId"]');
                    if (input && input.value === rid) {
                        forms[i].submit();
                        return 'submitted';
                    }
                }
                return 'form-not-found';
            """, reservation_id)
            log.info(f"      JS form.submit() → {submit_result}")
            if submit_result != 'submitted':
                continue
        except Exception as e:
            log.warning(f"      form.submit faalde: {e}")
            continue

        try:
            time.sleep(5)  # geef AJAX-navigatie + modal-render tijd

            spelers_info = driver.execute_script("""
                var resultaat = { medespelers: [], debug: {} };

                // Detail-modal: ETV kan spelers in een Bootstrap-modal renderen
                // ipv aparte page-navigatie. Check op visible modal eerst.
                var modal = document.querySelector('.modal.show, .modal.in, [role="dialog"]:not([style*="display: none"])');
                if (modal) {
                    resultaat.debug.modalAanwezig = true;
                    resultaat.debug.modalHtml600 = modal.outerHTML.slice(0, 600);
                }

                // Primaire route: #youPlayWith — zelfde structuur als de
                // bevestig-stap bij een nieuwe boeking
                var ypw = document.getElementById('youPlayWith');
                if (ypw) {
                    var h6s = ypw.querySelectorAll('h6');
                    h6s.forEach(function(h) {
                        var t = (h.innerText || '').trim();
                        if (t) resultaat.medespelers.push(t);
                    });
                    resultaat.debug.youPlayWith = h6s.length;
                }

                // Fallback 1: zoek elements met 'partner', 'speler',
                // 'deelnemer', 'companion' in class-name
                if (!resultaat.medespelers.length) {
                    var keywords = ['partner','deelnemer','companion','medespeler'];
                    document.querySelectorAll('[class*="partner"], [class*="deelnemer"], [class*="companion"], [class*="medespeler"]').forEach(function(el) {
                        var t = (el.innerText || '').trim();
                        if (t && t.length < 80 && t.length > 3) {
                            resultaat.medespelers.push(t);
                        }
                    });
                    resultaat.debug.fallback1 = resultaat.medespelers.length;
                }

                // Body-tekst-dump voor diagnose (eerste 800 voor modal-content)
                try {
                    resultaat.debug.body800 = document.body.innerText.slice(0, 800);
                } catch(e) {}
                resultaat.debug.url = location.href;
                return resultaat;
            """)

            medespelers = spelers_info.get('medespelers', []) if spelers_info else []
            log.info(f"      → debug: {spelers_info.get('debug') if spelers_info else 'no-result'}")

            if medespelers:
                # Dedup (in geval een speler dubbel matched op meerdere selectors)
                seen = set()
                unieke = []
                for naam in medespelers:
                    if naam not in seen:
                        seen.add(naam)
                        unieke.append(naam)
                r['spelers'] = unieke
                log.info(f"      ✅ Spelers: {unieke}")
            else:
                log.info(f"      ⚠️ Geen spelers gevonden — PWA toont alleen baan")
        except Exception as e:
            log.warning(f"  [{idx}] {rid}: spelers-scrape faalde ({e}) — skip")

    # Terug naar de overzichtspagina (cleaner dan driver.back())
    try:
        driver.get("https://www.etv-volley.nl/mijn/Reservations")
        time.sleep(2)
    except Exception:
        pass
    return reserveringen


def annuleer(driver, target_id: str) -> bool:
    """
    Vind en klik de annuleer-knop voor de reservering met deze ID.
    Returnt True als de reservering is verdwenen van de pagina.
    """
    log.info(f"Annuleren van reservering: {target_id}")

    # Parse target_id terug naar datum/tijd
    m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{4})_", target_id)
    if not m:
        log.error(f"❌ Ongeldige ID: {target_id}")
        return False
    doel_datum = m.group(1)
    doel_tijd  = f"{m.group(2)[:2]}:{m.group(2)[2:]}"

    # Probeer eerst /mijn/Reservations
    for url in RESERVERINGEN_URLS:
        driver.get(url)
        time.sleep(4)
        try:
            body = driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            body = ""
        if doel_datum in body or doel_tijd in body:
            log.info(f"Reservering lijkt zichtbaar op {url}")
            break
    else:
        log.warning("Reservering niet zichtbaar op een van de URLs — mogelijk al geannuleerd")
        return True

    # Zoek cancel-knop binnen rij/container die datum+tijd bevat
    gelukt = driver.execute_script("""
        var doelDatum = arguments[0];
        var doelTijd  = arguments[1];
        var rijen = document.querySelectorAll('table tr, li, div[class*="booking"], div[class*="reservation"], div[class*="reservering"]');
        for (var i = 0; i < rijen.length; i++) {
            var rij = rijen[i];
            var tekst = (rij.innerText || '').trim();
            if (tekst.indexOf(doelDatum) < 0 && tekst.indexOf(doelTijd) < 0) continue;
            // Vind cancel-knop binnen deze rij
            var btns = rij.querySelectorAll('button, a, [role="button"]');
            for (var j = 0; j < btns.length; j++) {
                var b = btns[j];
                var bt = (b.innerText || b.textContent || '').toLowerCase();
                var bc = (b.className || '').toString().toLowerCase();
                var ba = (b.getAttribute('aria-label') || '').toLowerCase();
                if (bt.indexOf('annuleer') >= 0 || bt.indexOf('cancel') >= 0
                    || bt.indexOf('verwijder') >= 0 || bt.indexOf('prullenbak') >= 0
                    || bc.indexOf('cancel') >= 0 || bc.indexOf('delete') >= 0
                    || bc.indexOf('annuleer') >= 0
                    || ba.indexOf('annuleer') >= 0 || ba.indexOf('cancel') >= 0) {
                    b.scrollIntoView({block:'center'});
                    b.click();
                    return 'geklikt: ' + (b.innerText || bc).slice(0, 60);
                }
            }
        }
        return null;
    """, doel_datum, doel_tijd)

    if not gelukt:
        log.error(f"❌ Geen annuleer-knop gevonden voor {doel_datum} {doel_tijd}")
        screenshot(driver, "annuleer_geen_knop")
        return False

    log.info(f"Cancel-knop {gelukt}")
    time.sleep(2)

    # ETV kan een bevestigingsdialoog tonen — klik 'Ja'/'Bevestig'
    try:
        for xpath in [
            "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ja')]",
            "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'bevestig')]",
            "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'annuleer')]",
            "//button[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ok')]",
        ]:
            try:
                els = WebDriverWait(driver, 3).until(
                    EC.presence_of_all_elements_located((By.XPATH, xpath))
                )
                for el in els:
                    if el.is_displayed() and el.is_enabled():
                        driver.execute_script("arguments[0].click();", el)
                        log.info(f"  Bevestigd: '{el.text.strip()[:40]}'")
                        time.sleep(2)
                        break
                break
            except Exception:
                pass
    except Exception:
        pass

    time.sleep(3)
    screenshot(driver, "annuleer_na_klik")

    # Verifieer: ververs pagina en kijk of reservering weg is
    driver.get(RESERVERINGEN_URLS[0])
    time.sleep(4)
    try:
        body_na = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        body_na = ""
    weg = (doel_datum not in body_na) and (doel_tijd not in body_na)
    if weg:
        log.info(f"✅ Reservering {target_id} succesvol geannuleerd")
    else:
        log.warning(f"⚠️ Reservering {target_id} mogelijk nog aanwezig (datum/tijd nog zichtbaar)")
    return weg


def verwijder_uit_agenda(datum: str, tijd: str) -> bool:
    """Verwijder de matching Padel-event uit Google Agenda voor (datum, tijd)."""
    if not GOOGLE_CREDENTIALS:
        log.warning("⚠️ GOOGLE_CALENDAR_CREDENTIALS niet ingesteld — agenda-verwijdering overgeslagen")
        return False
    try:
        from datetime import timedelta
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_service_account_info(
            json.loads(GOOGLE_CREDENTIALS),
            scopes=["https://www.googleapis.com/auth/calendar"]
        )
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        # Booking time is NL-lokaal. Maak datetime timezone-aware in Europe/Amsterdam
        # zodat het zoekvenster overeenkomt met het tijdstip waarop Google
        # Calendar het event heeft opgeslagen (timeZone="Europe/Amsterdam").
        try:
            from zoneinfo import ZoneInfo
            tz_nl = ZoneInfo("Europe/Amsterdam")
            start_dt = datetime.strptime(f"{datum} {tijd}", "%Y-%m-%d %H:%M").replace(tzinfo=tz_nl)
        except ImportError:
            # Fallback voor Python <3.9 — bepaal CEST/CET via maand
            start_dt = datetime.strptime(f"{datum} {tijd}", "%Y-%m-%d %H:%M")
            offset = "+02:00" if 4 <= start_dt.month <= 10 else "+01:00"
            tz_offset_str = offset

        # Window: -1u tot +2u rond het slot
        time_min = (start_dt - timedelta(hours=1)).isoformat()
        time_max = (start_dt + timedelta(hours=2)).isoformat()
        if not time_min.endswith(('Z', '+01:00', '+02:00', '-01:00', '-02:00')) and 'T' in time_min:
            # Fallback-pad zonder zoneinfo — voeg expliciete offset toe
            time_min += tz_offset_str
            time_max += tz_offset_str

        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            q="Padel",
            singleEvents=True,
        ).execute()
        events = events_result.get('items', [])
        log.info(f"  Agenda-zoekvenster {time_min} → {time_max}: {len(events)} 'Padel'-event(s) gevonden")

        # Match op datum+tijd substring (zonder timezone)
        target_dt_local = start_dt.strftime("%Y-%m-%dT%H:%M")
        verwijderd = 0
        for ev in events:
            ev_start = ev.get('start', {}).get('dateTime', '')
            ev_summary = ev.get('summary', '')
            # Match op start-datetime prefix (negeer tz-suffix) en 'Padel' in summary
            if target_dt_local in ev_start and 'Padel' in ev_summary:
                ev_id = ev.get('id')
                log.info(f"  Verwijder: '{ev_summary}' (start {ev_start})")
                service.events().delete(
                    calendarId=GOOGLE_CALENDAR_ID, eventId=ev_id
                ).execute()
                verwijderd += 1

        if verwijderd > 0:
            log.info(f"✅ {verwijderd} agenda-event(s) verwijderd")
            return True
        log.warning(f"⚠️ Geen matching Padel-event in agenda voor {datum} {tijd}")
        return False
    except ImportError:
        log.error("❌ google-api-python-client niet geïnstalleerd")
        return False
    except json.JSONDecodeError:
        log.error("❌ GOOGLE_CALENDAR_CREDENTIALS is geen geldig JSON")
        return False
    except Exception as e:
        log.error(f"❌ Agenda-verwijdering mislukt: {e}")
        return False


def commit_en_push(bestanden: list, message: str):
    """Commit en push de gegeven bestanden, met retry op race conditions."""
    import subprocess
    try:
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "config", "user.name",  "knltb-autoboek-bot"], check=True)
        subprocess.run(["git", "add"] + bestanden, check=True)
        # Check of er iets te committen valt
        result = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if result.returncode == 0:
            log.info("Geen wijzigingen — niets te committen")
            return True
        subprocess.run(["git", "commit", "-m", message], check=True)
    except subprocess.CalledProcessError as e:
        log.error(f"git commit faalde: {e}")
        return False

    for poging in range(1, 6):
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
        if subprocess.run(["git", "push"]).returncode == 0:
            log.info(f"✅ Gecommit en gepusht (poging {poging})")
            return True
        log.warning(f"Push poging {poging} mislukt — retry na {poging}s")
        time.sleep(poging)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cancel", help="ID van te annuleren reservering", default=None)
    args = parser.parse_args()

    if not BONDSNUMMER or not WACHTWOORD:
        log.error("❌ Stel KNLTB_BONDSNUMMER en KNLTB_WACHTWOORD in als GitHub Secrets")
        sys.exit(1)

    driver = maak_driver()
    try:
        if not login(driver):
            sys.exit(1)

        if args.cancel:
            etv_ok = annuleer(driver, args.cancel)
            if not etv_ok:
                log.error("❌ Annuleren op ETV-site mislukt")
            # Ook agenda-event verwijderen (zelfs als ETV-cancel mislukte, beter
            # een lege agenda dan een spookafspraak)
            m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{4})_", args.cancel)
            if m:
                verwijder_uit_agenda(m.group(1), f"{m.group(2)[:2]}:{m.group(2)[2:]}")
        # Always scrape (na annuleren is dit de bijgewerkte lijst)
        reserveringen = scrape_reserveringen(driver)

        # Per reservering de spelers ophalen via de Wijzig-flow.
        # Best-effort: faalt voor één item ⇒ blijft 'spelers' weg ⇒ PWA
        # toont alleen de baan (graceful degradation).
        reserveringen = scrape_spelers_per_reservering(driver, reserveringen)

        # Diagnose-velden (beginnen met '_') strippen voor we naar JSON
        # schrijven — die zijn alleen voor de scrape zelf bedoeld.
        for r in reserveringen:
            for k in [k for k in r if k.startswith('_')]:
                del r[k]

        # Schrijf JSON
        with open("reserveringen.json", "w", encoding="utf-8") as fh:
            json.dump({
                "bijgewerkt": datetime.now().isoformat(timespec="seconds"),
                "reserveringen": reserveringen,
            }, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        log.info(f"📄 reserveringen.json geschreven ({len(reserveringen)} items)")

    finally:
        driver.quit()

    actie = f"annuleer {args.cancel}" if args.cancel else "lees lijst"
    if not commit_en_push(
        ["reserveringen.json"],
        f"reserveringen: {actie} ({len(reserveringen)} actief)"
    ):
        log.error("❌ commit/push mislukt")
        sys.exit(1)


if __name__ == "__main__":
    main()

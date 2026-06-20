"""
etv_common.py — gedeelde ETV-login flow voor alle scripts.

Tot juni 2026 had elk script (boek_baan.py, lees_reserveringen.py,
haal_leden_op.py) een eigen ~70-130 regels login()-functie. Drift-risico:
een anti-bot-fix in één file → andere twee blijven achter (zie Recent-
paneel-race-fix die alleen in boek_baan.py zat tot deze refactor).

Deze module biedt één canonieke login(). De scripts roepen 'm aan
met hun eigen `screenshot` callback en credentials. Houd 't pure: geen
module-level state, geen globale Selenium-instance.

ROADMAP: boek_baan.py gebruikt voorlopig nog zijn eigen login() omdat
die op het kritieke cron-pad zit en niet veld-getest is tegen deze
shared implementatie. Migreer pas zodra de huidige booking-flow
stabiel is bewezen.
"""

import logging
import time

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

log = logging.getLogger(__name__)


def login(driver, bondsnummer: str, wachtwoord: str,
          login_url: str = "https://www.etv-volley.nl/Login",
          screenshot=None) -> bool:
    """
    Log in op de ETV/KNLTB.Club portal.

    Returns True bij success, False bij fail.

    screenshot: optionele callable(driver, naam). Wordt aangeroepen op
                vaste momenten ('01_login_pagina', '02_na_login',
                '02b_login_mislukt', 'login_fout'). Default = no-op.

    Detecteert vele varianten van gebruikers/wachtwoord/submit velden
    (placeholders, name-attribuut, id-attribuut). Vult via JS native
    setters zodat React/Vue input-events triggeren (anti-bot-bestendig).
    """
    if screenshot is None:
        screenshot = lambda _d, _n: None

    log.info(f"Navigeer naar {login_url}")
    driver.get(login_url)
    time.sleep(4)
    screenshot(driver, "01_login_pagina")

    # Cookie-banner accepteren (met expliciete wacht — XPath case-
    # insensitive via translate-truc)
    for sel in [
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accepteren')]",
        "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
        "//a[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accepteren')]",
    ]:
        try:
            knop = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, sel))
            )
            knop.click()
            log.info("Cookie-banner geaccepteerd")
            time.sleep(1)
            break
        except Exception:
            pass

    try:
        gebruiker_veld = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH,
                "//input[@type='text' or @type='email' "
                "or @name='username' or @name='Username' or @name='UserName' "
                "or @id='username' or @id='Username' or @id='UserName' "
                "or contains(@placeholder,'bondsnummer') "
                "or contains(@placeholder,'gebruikersnaam') "
                "or contains(@placeholder,'e-mail') "
                "or contains(@placeholder,'email')]"))
        )

        # JS-fill triggert ook React/Vue/Vanilla framework-listeners
        driver.execute_script("""
            var el = arguments[0], val = arguments[1];
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, gebruiker_veld, bondsnummer)
        log.info(f"Bondsnummer ingevuld via JS ({len(bondsnummer)} tekens)")

        ww_veld = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//input[@type='password']"))
        )
        driver.execute_script("""
            var el = arguments[0], val = arguments[1];
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(el, val);
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        """, ww_veld, wachtwoord)
        log.info(f"Wachtwoord ingevuld via JS ({len(wachtwoord)} tekens)")
        time.sleep(1)

        # Zichtbare submit-knop vinden (niet de cookie-banner!)
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
            log.warning("Geen submit-knop gevonden — Keys.RETURN als fallback")
            ww_veld.send_keys(Keys.RETURN)

        time.sleep(6)
        screenshot(driver, "02_na_login")
        log.info(f"URL na login: {driver.current_url}")

        # Wachtwoordveld nog zichtbaar = login mislukt
        try:
            pw = driver.find_element(By.XPATH, "//input[@type='password']")
            if pw.is_displayed():
                log.error("❌ Login mislukt — wachtwoordveld nog zichtbaar")
                screenshot(driver, "02b_login_mislukt")
                return False
        except Exception:
            pass  # Veld weg = succes

        log.info("✅ Ingelogd!")
        return True
    except TimeoutException as e:
        log.error(f"❌ Login timeout: {e}")
        screenshot(driver, "login_fout")
        return False

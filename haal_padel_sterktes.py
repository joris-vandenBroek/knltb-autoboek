"""
Haal padel speelsterktes op van mijnknltb.toernooi.nl en voeg toe aan leden.json.

Strategie:
- Geen Selenium nodig: mijnknltb.toernooi.nl heeft geen Cloudflare-bescherming.
- requests.Session + CSRF-token voor login
- GET /find/player/DoSearch?Query={bondsnummer} â†’ player-profile link
- GET /player-profile/{guid} â†’ padel sterkte uit server-rendered HTML
"""

import os, sys, json, re, logging
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger(__name__)

MIJNKNLTB_URL = "https://mijnknltb.toernooi.nl"
BONDSNUMMER = os.environ.get("KNLTB_LOGINNAAM", "")
WACHTWOORD     = os.environ.get("KNLTB_WACHTWOORD", "")
MAX_LEDEN     = int(os.environ.get("MAX_LEDEN", "0") or "0")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def maak_sessie() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def accepteer_cookiewall(session: requests.Session) -> None:
    """
    Accepteer de cookie wall als die verschijnt.
    De wall staat op /cookiewall en heeft een formulier met een 'Akkoord'-knop.
    """
    r = session.get(f"{MIJNKNLTB_URL}/cookiewall", timeout=15,
                    params={"returnurl": "/user/login"})
    if "cookiewall" not in r.url.lower():
        log.info("Geen cookie wall aangetroffen")
        return

    log.info("Cookie wall gevonden â€” accepteren...")

    # Zoek form action en CSRF token in de cookie wall
    action_m = re.search(r'<form[^>]+action="([^"]*cookiewall[^"]*)"', r.text, re.I)
    action = action_m.group(1) if action_m else "/cookiewall"
    if not action.startswith("http"):
        action = MIJNKNLTB_URL + action

    token_m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', r.text)
    token = token_m.group(1) if token_m else ""

    # POST acceptatie (knop 'Akkoord')
    session.post(
        action,
        data={
            "__RequestVerificationToken": token,
            "AcceptAll": "true",   # gangbare veldnaam voor 'Akkoord'
            "returnUrl": "/user/login",
        },
        headers={"Referer": r.url},
        timeout=15,
        allow_redirects=True,
    )
    log.info("Cookie wall geaccepteerd")


def login(session: requests.Session) -> bool:
    """Login op mijnknltb via requests. Geeft True als geslaagd."""
    # Stap 0: accepteer eventuele cookie wall
    accepteer_cookiewall(session)

    log.info("GET login-pagina voor CSRF-token...")
    r = session.get(f"{MIJNKNLTB_URL}/user/login", timeout=20, allow_redirects=True)

    # Als we nog steeds op de cookie wall zitten, harder accepteren
    if "cookiewall" in r.url.lower():
        log.warning("Cookie wall nog steeds actief â€” probeer via GET-parameter")
        session.get(f"{MIJNKNLTB_URL}/cookiewall",
                    params={"returnurl": "/user/login", "accept": "true"},
                    timeout=10)
        r = session.get(f"{MIJNKNLTB_URL}/user/login", timeout=20, allow_redirects=True)

    if r.status_code != 200:
        log.error(f"Login-pagina niet bereikbaar: {r.status_code} {r.url}")
        return False

    # Log waar we nu zijn
    log.info(f"Login-pagina URL: {r.url}")

    # Extract __RequestVerificationToken
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', r.text)
    if not m:
        m = re.search(r'value="([^"]+)"[^>]*name="__RequestVerificationToken"', r.text)
    token = m.group(1) if m else ""
    if not token:
        log.warning("Geen CSRF-token gevonden â€” toch proberen")
        snippet = re.sub(r'\s+', ' ', r.text)[:400]
        log.warning(f"Pagina snippet: {snippet!r}")
    else:
        log.info(f"CSRF-token gevonden (len={len(token)})")

    # Log alle form input velden op de loginpagina (ter debug)
    form_inputs = re.findall(r'<input[^>]+>', r.text, re.I)
    for inp in form_inputs:
        name_m  = re.search(r'name="([^"]*)"', inp, re.I)
        type_m  = re.search(r'type="([^"]*)"', inp, re.I)
        value_m = re.search(r'value="([^"]*)"', inp, re.I)
        inp_name  = name_m.group(1)  if name_m  else "(no name)"
        inp_type  = type_m.group(1)  if type_m  else "(no type)"
        inp_value = value_m.group(1) if value_m else ""
        if inp_type.lower() != "password":
            log.info(f"  Form input: name={inp_name!r} type={inp_type!r} value={inp_value[:40]!r}")
        else:
            log.info(f"  Form input: name={inp_name!r} type={inp_type!r} value=***")

    # ReturnUrl is standaard aanwezig in ASP.NET Identity login forms
    return_url_m = re.search(r'name="ReturnUrl"[^>]*value="([^"]*)"', r.text, re.I)
    return_url = return_url_m.group(1) if return_url_m else ""

    log.info(f"POST login als gebruiker {BONDSNUMMER[:4]}*** (len={len(BONDSNUMMER)}), "
             f"wachtwoord len={len(WACHTWOORD)}, ReturnUrl={return_url!r}...")
    r = session.post(
        f"{MIJNKNLTB_URL}/user/login",
        data={
            "Login": BONDSNUMMER,
            "Password": WACHTWOORD,
            "__RequestVerificationToken": token,
            "ReturnUrl": return_url,
        },
        headers={"Referer": f"{MIJNKNLTB_URL}/user/login"},
        timeout=20,
        allow_redirects=True,
    )

    if "login" in r.url.lower() or "cookiewall" in r.url.lower():
        log.error(f"Login mislukt: {r.url}")
        # Log de response headers voor clues
        for k, v in r.headers.items():
            log.error(f"  Response header: {k}: {v}")
        # Log form inputs van de login-response om foutmelding te zien
        error_m = re.search(r'class="[^"]*error[^"]*"[^>]*>(.*?)</[a-z]+>', r.text, re.DOTALL | re.I)
        if error_m:
            log.error(f"  Foutmelding op pagina: {re.sub(r'<[^>]+>', '', error_m.group(1)).strip()!r}")
        snippet = re.sub(r'\s+', ' ', r.text)[:600]
        log.error(f"  Response snippet: {snippet!r}")
        return False

    log.info(f"Login geslaagd: {r.url}")
    return True


def controleer_sessie(session: requests.Session) -> bool:
    """Controleer of sessie nog geldig is via snelle HEAD-request."""
    try:
        r = session.get(f"{MIJNKNLTB_URL}/user", timeout=10, allow_redirects=True)
        geldig = "login" not in r.url.lower()
        if not geldig:
            log.warning(f"Sessie verlopen (redirect naar {r.url})")
        return geldig
    except Exception as e:
        log.warning(f"Sessie-check fout: {e}")
        return False


def herstel_sessie(session: requests.Session) -> bool:
    """Herlogin als sessie verlopen is."""
    log.info("Sessie herstellen via herlogin...")
    return login(session)


def zoek_profiel_url(session: requests.Session, bondsnummer: str) -> str | None:
    """Zoek player-profile URL via DoSearch AJAX endpoint."""
    try:
        r = session.get(
            f"{MIJNKNLTB_URL}/find/player/DoSearch",
            params={"Query": bondsnummer, "Page": "1", "SportID": "0"},
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{MIJNKNLTB_URL}/find/player",
                "Accept": "text/html, */*; q=0.01",
            },
            timeout=15,
        )
        if "login" in r.url.lower():
            log.warning(f"  DoSearch: redirect naar login voor {bondsnummer}")
            return None

        matches = re.findall(r'href="/player-profile/([^"]+)"', r.text)
        if matches:
            log.info(f"  DoSearch: {len(matches)} resultaat/resultaten voor {bondsnummer}")
            return f"{MIJNKNLTB_URL}/player-profile/{matches[0]}"

        log.warning(f"  DoSearch: geen profiellink voor {bondsnummer} "
                    f"(status={r.status_code}, len={len(r.text)})")
        if len(r.text) < 200:
            log.warning(f"  Response: {r.text!r}")
        return None
    except Exception as e:
        log.warning(f"  DoSearch fout ({bondsnummer}): {e}")
        return None


def haal_padel_sterkte_van_profiel(session: requests.Session, profiel_url: str,
                                   bondsnummer: str) -> dict | None:
    """
    Haal padel sterkte op van player-profile pagina.
    Geeft {'sterkte': '7', 'rating': '7,32'} of {} bij geen padel-rating,
    of None als sessie verlopen.
    """
    try:
        r = session.get(
            profiel_url,
            headers={"Referer": f"{MIJNKNLTB_URL}/find/player"},
            timeout=15,
        )
        if "login" in r.url.lower():
            log.warning(f"  Profiel: sessie verlopen ({r.url})")
            return None  # signaal: sessie verlopen

        m = re.search(
            r'title="Padel Dubbel"[^>]*>.*?'
            r'<span class="tag-duo__title">(.*?)</span>.*?'
            r'<span class="tag-duo__value">(.*?)</span>',
            r.text, re.DOTALL
        )
        if m:
            sterkte = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            rating  = m.group(2).strip()
            log.info(f"  âœ… {bondsnummer}: sterkte={sterkte!r}, rating={rating!r}")
            return {"sterkte": sterkte, "rating": rating}

        log.info(f"  Geen Padel Dubbel rating voor {bondsnummer}")
        return {}
    except Exception as e:
        log.warning(f"  Profiel fout ({bondsnummer}): {e}")
        return {}


def haal_padel_sterkte(session: requests.Session, bondsnummer: str, idx: int = 0) -> dict:
    """Volledig ophaalproces voor Ã©Ã©n lid. Geeft {'sterkte':..., 'rating':...} of {}."""

    # Stap 1: zoek profiel-URL
    profiel_url = zoek_profiel_url(session, bondsnummer)
    if profiel_url is None:
        # Sessie mogelijk verlopen â€” herstellen en opnieuw proberen
        if herstel_sessie(session):
            profiel_url = zoek_profiel_url(session, bondsnummer)
    if not profiel_url:
        log.warning(f"  âŒ Geen profiel gevonden voor {bondsnummer}")
        return {}

    # Stap 2: haal sterkte op van profielpagina
    result = haal_padel_sterkte_van_profiel(session, profiel_url, bondsnummer)
    if result is None:
        # Sessie verlopen
        if herstel_sessie(session):
            result = haal_padel_sterkte_van_profiel(session, profiel_url, bondsnummer)
    return result or {}


def main():
    if not BONDSNUMMER or not WACHTWOORD:
        log.error("Stel KNLTB_LOGINNAAM en KNLTB_WACHTWOORD in als GitHub Secrets")
        sys.exit(1)

    try:
        with open("leden.json", encoding="utf-8") as f:
            leden_lijst = json.load(f)
    except Exception as e:
        log.error(f"Kan leden.json niet lezen: {e}")
        sys.exit(1)

    leden_lijst = [
        item if isinstance(item, dict) else {"naam": item, "bondsnummer": ""}
        for item in leden_lijst
    ]

    te_verwerken = leden_lijst[:MAX_LEDEN] if MAX_LEDEN > 0 else leden_lijst
    if MAX_LEDEN > 0:
        log.info(f"MAX_LEDEN={MAX_LEDEN}: verwerk eerste {MAX_LEDEN} van {len(leden_lijst)} leden")

    met_bondsnummer = [l for l in te_verwerken if l.get("bondsnummer", "").strip()]
    log.info(f"{len(te_verwerken)} leden te verwerken, {len(met_bondsnummer)} met bondsnummer")

    session = maak_sessie()
    if not login(session):
        log.error("Login mislukt â€” script stopt")
        sys.exit(1)

    # Elke 100 leden sessie controleren en zonodig herstellen
    for i, lid in enumerate(te_verwerken):
        bnr = lid.get("bondsnummer", "").strip()
        if not bnr:
            log.info(f"  [{i+1}/{len(leden_lijst)}] {lid['naam']}: geen bondsnummer")
            lid.setdefault("sterkte_padel", "")
            lid.setdefault("rating_padel", "")
            continue

        if i > 0 and i % 100 == 0:
            if not controleer_sessie(session):
                herstel_sessie(session)

        log.info(f"[{i+1}/{len(leden_lijst)}] {lid['naam']} ({bnr})")
        data = haal_padel_sterkte(session, bnr, idx=i)
        lid["sterkte_padel"] = data.get("sterkte", "")
        lid["rating_padel"]  = data.get("rating", "")

    with open("leden.json", "w", encoding="utf-8") as f:
        json.dump(leden_lijst, f, ensure_ascii=False, indent=2)

    met_sterkte = sum(1 for l in leden_lijst if l.get("sterkte_padel"))
    log.info(f"Klaar: sterkte aanwezig voor {met_sterkte}/{len(leden_lijst)} leden")


if __name__ == "__main__":
    main()



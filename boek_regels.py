"""
Dependency-vrije regels voor boek_baan.py.

Net als wachtrij_regels.py bewust zonder selenium/undetected_chromedriver, zodat
deze logica in tests draait zonder browser. boek_baan.py importeert hieruit.
"""

from datetime import datetime, timedelta

PADEL_BANEN = ["Padel 4", "Padel 6", "Padel 5", "Padel 3", "Padel 2", "Padel 1"]
TENNIS_BANEN = ["Tennis 04", "Tennis 05", "Tennis 06", "Tennis 07",
                "Tennis 08", "Tennis 09", "Tennis 11", "Tennis 12"]


def banen_voor_sport(sport: str) -> list:
    """Banenlijst voor een sport. Onbekende sport valt terug op padel."""
    return TENNIS_BANEN if (sport or "").strip().lower() == "tennis" else PADEL_BANEN


def baan_uit_body(body: str, sport: str, verwachte_baan: str = "") -> str:
    """
    Lees de baannaam uit de tekst van de reserveringsoverzichtspagina.

    Zoekt uitsluitend in de banen van de GEBOEKTE sport. De oude implementatie
    zocht altijd in PADEL_BANEN en viel anders terug op de kale string 'Padel';
    daardoor werd een tennisboeking op Tennis 12 als 'Padel 3' weggeschreven
    (run #198, 09-08-2026) — 'Padel 3' hoorde bij een andere reservering die
    toevallig ook op de overzichtspagina stond.

    `verwachte_baan` is de baan die tijdens de grid-klik is gekozen. Staat die
    in de body, dan wint hij: de overzichtspagina toont meerdere reserveringen
    en volgorde is geen betrouwbare tiebreaker.

    Geeft '' als er geen baan van deze sport in de body staat — bewust geen
    terugval op een generieke naam, want een verkeerde baan sturen we door naar
    de agenda en de boekstatus.
    """
    if not body:
        return ""
    banen = banen_voor_sport(sport)
    if verwachte_baan and verwachte_baan in banen and verwachte_baan in body:
        return verwachte_baan
    return next((b for b in banen if b in body), "")


def baan_voorkeur(gebruiker: str, sport: str, gebruiker_ids=None) -> list:
    """
    Voorkeursvolgorde van banen voor dit account.

    Padel: elk account start op een andere baan (in PADEL_BANEN-volgorde) en
    rolt door. Run #199/#200 (09-08-2026) liet zien waarom: Joris en Toine
    wilden allebei padel om 20:00, vuurden op dezelfde seconde, en een vaste
    sortering liet ze allebei naar dezelfde eerste baan grijpen. Dat is
    zelfgemaakte concurrentie — bij schaarste verliest er per definitie één.
    PADEL_BANEN staat op voorkeursvolgorde (26-08-2026: 4, 6, 5, 3, 2, 1);
    spreiden zorgt ervoor dat niet alle accounts tegelijk naar baan 4 grijpen.

    De offset komt uit de positie in de (gesorteerde) gebruikerslijst, niet uit
    een hash of toeval: dat spreidt N accounts gelijkmatig over de banen, botst
    gegarandeerd niet bij N <= 6, blijft gelijk als gebruikers.json herordend
    wordt, en houdt logs tussen runs vergelijkbaar.

    Tennis blijft ongemoeid: daar is hoogste baan eerst een bewuste keuze omdat
    baan 04 de slechtste is (commit e9a76b1). Spreiden zou dat terugdraaien.
    """
    banen = banen_voor_sport(sport)
    if (sport or "").strip().lower() == "tennis":
        return list(reversed(banen))

    ids = sorted(gebruiker_ids or [])
    if not ids or gebruiker not in ids:
        return list(banen)

    offset = (ids.index(gebruiker) * len(banen)) // len(ids)
    return list(banen[offset:]) + list(banen[:offset])


def boeking_op_datum(reserveringen, datum: str):
    """
    Zoek een bestaande reservering op deze speeldatum, of None.

    ETV staat één actieve boeking per dag per lid toe. Run #203 (09-08-2026)
    liep vijf pogingen stuk op een baan die vrij was maar nooit bevestigd kon
    worden, omdat het account die dag al op Padel 5 stond; de melding
    "kan 1 actieve boekingen per dag hebben" kwam pas ná de bevestig-POST.

    Bewust tolerant voor rommel: een mislukte of onvolledige scrape mag nooit
    een boeking blokkeren. Bij twijfel geeft deze functie None terug, zodat we
    het gewoon proberen — een overbodige poging is goedkoper dan een gemiste
    baan.
    """
    if not reserveringen or not datum:
        return None
    for r in reserveringen:
        if isinstance(r, dict) and r.get("datum") == datum:
            return r
    return None


def wizard_ververs_moment(nu: datetime, doel_window_open: datetime,
                          marge_s: float = 45):
    """
    Wanneer de wizard nog even ververst moet worden vóór het startsein, of None.

    Het script logt rond 06:52 in en bouwt de wizard meteen op, om daarna tot
    07:00 stil te staan op ReservationsDay. Juist die 8 minuten idle maakten het
    formulier onbruikbaar (run #199/#200, 09-08-2026). Door vlak voor het
    startsein te herladen begint de spits met een verse sessie.

    Geeft None als er te weinig tijd meer is. Verversen kan ons namelijk terug
    naar de spelerspagina sturen — dat gebeurde in de outer-retry van 09-08 —
    en dan moet er ruimte zijn om de wizard opnieuw op te bouwen. Te laat
    verversen is erger dan niet verversen.
    """
    moment = doel_window_open - timedelta(seconds=marge_s)
    return moment if moment > nu else None


def dag_selectie_actie(nu: datetime, fase_start: datetime, budget_s: float,
                       hard_stop: datetime) -> str:
    """
    Bepaal wat er moet gebeuren als de dag-selectie blijft falen.

    Geeft 'doorgaan', 'herstart' of 'stop'.

    Achtergrond (run #199/#200, 09-08-2026): het script logt rond 06:52 in en
    wacht daarna op ReservationsDay tot 07:00:01. Na die 8 minuten idle
    accepteert ETV de dagdeel-submit niet meer — 34 pogingen lang geen
    navigatie. Een volledig verse wizard doet het daarna in poging 1, binnen
    ~2s (bevestigd in de run van 07-08 om 13:13, 20+ keer achtereen). De oude
    absolute deadline van 07:03:00 liet het script dus 3 minuten op een dode
    sessie hameren; om 07:04 was alle padel weg.

    Het budget is RELATIEF aan `fase_start` (het begin van de dag-selectie
    binnen déze wizard-poging), niet aan de wandklok. Anders zou een herstart
    die zelf tijd kost meteen weer over een absolute deadline heen zijn en in
    één seconde alle outer-pogingen opbranden.

    `hard_stop` is de absolute bovengrens: daarna heeft doorgaan geen zin meer.
    """
    if nu >= hard_stop:
        return "stop"
    if (nu - fase_start).total_seconds() > budget_s:
        return "herstart"
    return "doorgaan"

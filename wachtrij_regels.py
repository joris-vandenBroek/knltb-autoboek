"""
Pure datum- en padlogica rond wachtrij-items.

Bewust vrij van selenium-, google- en requests-imports, zodat zowel
genereer_herhalingen.py als lees_reserveringen.py deze module kan gebruiken
en hij zonder zware dependencies testbaar is.
"""

from datetime import date, datetime, timedelta

WEEKDAGEN = {
    "maandag": 0,
    "dinsdag": 1,
    "woensdag": 2,
    "donderdag": 3,
    "vrijdag": 4,
    "zaterdag": 5,
    "zondag": 6,
}

# verwerk_wachtrij.yml triggert een item op speeldatum - 2 om 06:50. Een item
# voor overmorgen kan die trigger dus al gemist hebben; daarom genereren we
# nooit dichterbij dan 3 dagen.
MIN_VOORUIT_DAGEN = 3


def weekdag_nummer(naam: str) -> int:
    """'dinsdag' -> 1. Raises ValueError bij een onbekende weekdagnaam."""
    sleutel = (naam or "").strip().lower()
    if sleutel not in WEEKDAGEN:
        raise ValueError(f"Onbekende weekdag: {naam!r}")
    return WEEKDAGEN[sleutel]


def parse_datum(s: str) -> date:
    """'2026-08-11' -> date(2026, 8, 11). Raises ValueError bij ongeldig formaat."""
    return datetime.strptime(s, "%Y-%m-%d").date()


def tijd_slug(tijd: str) -> str:
    """'20:00' -> '2000' (voor de wachtrij-bestandsnaam)."""
    return tijd.replace(":", "")


def wachtrij_pad(gebruiker: str, datum: str, tijd: str) -> str:
    """Pad van een wachtrij-item, altijd met forward slashes."""
    return f"wachtrij/{gebruiker}/{datum}_{tijd_slug(tijd)}.json"


def is_verlopen(datum: str, vandaag: date) -> bool:
    """
    True als de speeldatum vóór vandaag ligt.

    Een onleesbare datum geldt bewust als niet-verlopen: liever een item laten
    staan dan data weggooien op een parse-fout.
    """
    try:
        return parse_datum(datum) < vandaag
    except (ValueError, TypeError):
        return False


def komende_weekdagen(weekdag: int, van: date, tot: date) -> list:
    """Alle data met die weekdag in [van, tot], oplopend gesorteerd."""
    if van > tot:
        return []
    eerste = van + timedelta(days=(weekdag - van.weekday()) % 7)
    resultaat = []
    huidige = eerste
    while huidige <= tot:
        resultaat.append(huidige)
        huidige += timedelta(days=7)
    return resultaat


def generatie_venster(gegenereerd_tot, vandaag: date, weken: int = 4):
    """
    Bepaal het venster [van, tot] waarin nieuwe items gegenereerd mogen worden.

    De ondergrens is nooit lager dan vandaag + MIN_VOORUIT_DAGEN. Dat is
    essentieel: staat een regel lang op actief:false, dan ligt de watermark ver
    in het verleden en zou 'watermark + 1' data in het verleden opleveren.
    """
    ondergrens = vandaag + timedelta(days=MIN_VOORUIT_DAGEN)
    if gegenereerd_tot:
        na_watermark = parse_datum(gegenereerd_tot) + timedelta(days=1)
        ondergrens = max(ondergrens, na_watermark)
    return ondergrens, vandaag + timedelta(days=weken * 7)

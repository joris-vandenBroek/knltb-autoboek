"""
Genereer wachtrij-items uit de herhaalregels in herhalingen.json.

Draait wekelijks via .github/workflows/genereer_herhalingen.yml. Schrijft
gewone wachtrij-items; de bestaande verwerk_wachtrij.yml pikt ze op.
"""

import json
import logging
import os
import re
import sys
from datetime import date, datetime

from wachtrij_regels import (
    generatie_venster,
    komende_weekdagen,
    wachtrij_pad,
    weekdag_nummer,
)

TIJD_PATROON = re.compile(r"[0-2]\d:[0-5]\d")
GELDIGE_SPORTEN = ("padel", "tennis")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

HERHALINGEN_FILE = "herhalingen.json"
GEBRUIKERS_FILE = "gebruikers.json"
LEDEN_FILE = "leden.json"


def valideer_regels(regels, gebruikers, leden_namen):
    """
    Controleer actieve herhaalregels. Retourneert een lijst foutmeldingen;
    een lege lijst betekent dat alles klopt.

    Verwacht alleen regels met actief=true -- een geparkeerde regel met een
    vertrokken speler mag de generatie van de rest niet blokkeren.
    """
    fouten = []
    naam_per_id = {g["id"]: g["naam"] for g in gebruikers}
    bezet_per_weekdag = {}

    for r in regels:
        rid = r.get("id", "<regel zonder id>")
        gebruiker = r.get("gebruiker", "")

        if gebruiker not in naam_per_id:
            fouten.append(
                f"{rid}: gebruiker '{gebruiker}' staat niet in gebruikers.json"
            )

        try:
            weekdag = weekdag_nummer(r.get("weekdag", ""))
        except ValueError:
            fouten.append(f"{rid}: onbekende weekdag '{r.get('weekdag')}'")
            weekdag = None

        if r.get("sport") not in GELDIGE_SPORTEN:
            fouten.append(
                f"{rid}: sport moet 'padel' of 'tennis' zijn, niet '{r.get('sport')}'"
            )

        if not TIJD_PATROON.fullmatch(str(r.get("tijd", ""))):
            fouten.append(f"{rid}: tijd '{r.get('tijd')}' moet formaat HH:MM hebben")

        spelers = r.get("spelers", [])
        if len(spelers) != 4:
            fouten.append(
                f"{rid}: precies 4 spelers vereist, gevonden {len(spelers)}"
            )
        elif gebruiker in naam_per_id and spelers[0] != naam_per_id[gebruiker]:
            fouten.append(
                f"{rid}: spelers[0] moet de boeker zijn "
                f"('{naam_per_id[gebruiker]}'), niet '{spelers[0]}'"
            )

        for naam in spelers:
            if naam not in leden_namen:
                fouten.append(f"{rid}: speler '{naam}' staat niet in leden.json")

        if weekdag is not None:
            bezet = bezet_per_weekdag.setdefault(weekdag, {})
            for naam in spelers:
                if naam in bezet:
                    fouten.append(
                        f"{rid}: speler '{naam}' zit ook in regel "
                        f"'{bezet[naam]}' op dezelfde weekdag -- ETV staat "
                        f"geen 2e reservering per lid toe"
                    )
                else:
                    bezet[naam] = rid

    return fouten


def maak_item(regel, datum, ingediend):
    """Bouw een wachtrij-item in exact het formaat dat verwerk_wachtrij.yml leest."""
    return {
        "gebruiker": regel["gebruiker"],
        "datum": datum,
        "tijd": regel["tijd"],
        "sport": regel["sport"],
        "spelers": list(regel["spelers"]),
        "ingediend": ingediend,
    }


def plan_items(regels, vandaag, bestaat, ingediend, weken=4):
    """
    Bepaal welke wachtrij-items aangemaakt moeten worden.

    Retourneert (nieuwe_items, bijgewerkte_regels), waarbij nieuwe_items een
    lijst (pad, item)-tupels is. Raakt het bestandssysteem niet: `bestaat` is
    een callable (pad) -> bool.

    De watermark `gegenereerd_tot` schuift op naar de laatste datum in het
    venster, ook als dat bestand al bestond. Daardoor kijkt een volgende run
    nooit meer naar die datum en komt een handmatig verwijderd item niet terug.
    """
    nieuwe = []
    bijgewerkt = []

    for oorspronkelijk in regels:
        r = dict(oorspronkelijk)
        if not r.get("actief", True):
            bijgewerkt.append(r)
            continue

        weekdag = weekdag_nummer(r["weekdag"])
        van, tot = generatie_venster(r.get("gegenereerd_tot"), vandaag, weken)

        laatste = None
        for dag in komende_weekdagen(weekdag, van, tot):
            datum = dag.isoformat()
            pad = wachtrij_pad(r["gebruiker"], datum, r["tijd"])
            if not bestaat(pad):
                nieuwe.append((pad, maak_item(r, datum, ingediend)))
            laatste = datum

        if laatste:
            r["gegenereerd_tot"] = laatste
        bijgewerkt.append(r)

    return nieuwe, bijgewerkt


def _laad_json(pad):
    with open(pad, encoding="utf-8") as fh:
        return json.load(fh)


def _schrijf_json(pad, data):
    with open(pad, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main():
    regels = _laad_json(HERHALINGEN_FILE)
    gebruikers = _laad_json(GEBRUIKERS_FILE)
    leden = _laad_json(LEDEN_FILE)
    leden_namen = {
        lid["naam"] for lid in leden if isinstance(lid, dict) and "naam" in lid
    }

    actieve = [r for r in regels if r.get("actief", True)]
    fouten = valideer_regels(actieve, gebruikers, leden_namen)
    if fouten:
        for fout in fouten:
            log.error(fout)
        log.error(f"{len(fouten)} validatiefout(en) -- er is niets aangemaakt")
        sys.exit(1)

    ingediend = datetime.now().isoformat(timespec="seconds")
    nieuwe, bijgewerkt = plan_items(regels, date.today(), os.path.exists, ingediend)

    for pad, item in nieuwe:
        os.makedirs(os.path.dirname(pad), exist_ok=True)
        _schrijf_json(pad, item)
        log.info(f"Aangemaakt: {pad}")

    _schrijf_json(HERHALINGEN_FILE, bijgewerkt)
    log.info(f"{len(nieuwe)} nieuw(e) wachtrij-item(s) aangemaakt")


if __name__ == "__main__":
    main()

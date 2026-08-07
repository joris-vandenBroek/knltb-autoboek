"""
Genereer wachtrij-items uit de herhaalregels in herhalingen.json.

Draait wekelijks via .github/workflows/genereer_herhalingen.yml. Schrijft
gewone wachtrij-items; de bestaande verwerk_wachtrij.yml pikt ze op.
"""

import re

from wachtrij_regels import weekdag_nummer

TIJD_PATROON = re.compile(r"[0-2]\d:[0-5]\d")
GELDIGE_SPORTEN = ("padel", "tennis")


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

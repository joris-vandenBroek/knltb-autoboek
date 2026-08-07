# Wekelijks terugkerende reserveringen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Een declaratieve herhaalregel (`herhalingen.json`) die zichzelf wekelijks uitvoert door wachtrij-items vooruit te genereren, zodat elke dinsdag 20:00 automatisch één tennisbaan onder Chris en twee padelbanen onder Toine en Joris geboekt worden.

**Architecture:** Alle datumlogica komt in een nieuwe, dependency-vrije module `wachtrij_regels.py`. Die wordt gebruikt door zowel de nieuwe generator (`genereer_herhalingen.py`) als de bestaande opruiming in `lees_reserveringen.py`. De generator schrijft gewone wachtrij-items; aan `boek.yml`, `verwerk_wachtrij.yml` en `boek_baan.py` verandert niets. Een watermark-veld `gegenereerd_tot` per regel zorgt dat de generator nooit achteruit kijkt, zodat een handmatig verwijderd item niet terugkomt.

**Tech Stack:** Python 3.11 (GitHub Actions) / 3.14 (lokaal), uitsluitend stdlib. Tests met `unittest` uit de stdlib — er is geen testframework in deze repo en pytest is niet geïnstalleerd. GitHub Actions YAML.

## Global Constraints

- **Geen nieuwe dependencies.** `genereer_herhalingen.py` en `wachtrij_regels.py` gebruiken alleen stdlib (`json`, `os`, `sys`, `re`, `logging`, `datetime`). `requirements.txt` wordt niet aangepast en de generator-workflow doet géén `pip install`.
- **`wachtrij_regels.py` mag nooit selenium, undetected_chromedriver of google-libs importeren.** Selenium is lokaal niet geïnstalleerd; een import daarvan maakt de module onbruikbaar in tests.
- **Geen wijzigingen aan** `boek.yml`, `verwerk_wachtrij.yml`, `boek_baan.py` of `docs/index.html`. Omdat `docs/` niet verandert, hoeft het `CACHE`-versienummer in `docs/sw.js` **niet** omhoog (`knltb-autoboek.md` sectie 7).
- **Wachtrij-itemformaat blijft exact zoals nu:** keys `gebruiker`, `datum`, `tijd`, `sport`, `spelers`, `ingediend`. Bestandsnaam `wachtrij/<gebruiker>/<YYYY-MM-DD>_<HHMM>.json`. `verwerk_wachtrij.yml` leest `.spelers[1]`, `.spelers[2]`, `.spelers[3]`.
- **`spelers[0]` is altijd de boeker zelf**, met exact de `naam` uit `gebruikers.json`.
- **Validatie geldt alleen voor regels met `actief: true`.** Een geparkeerde regel met een vertrokken speler mag de generatie van de andere regels niet blokkeren.
- Alle log- en foutmeldingen in het Nederlands, consistent met de rest van de repo.
- Tests staan in `tests/`, met een `tests/__init__.py` — zonder dat bestand faalt `unittest discover` met "Start directory is not importable".

---

### Task 1: Dependency-vrije datumlogica in `wachtrij_regels.py`

**Files:**
- Create: `wachtrij_regels.py`
- Create: `tests/__init__.py`
- Create: `tests/test_wachtrij_regels.py`

**Interfaces:**
- Consumes: niets (alleen stdlib).
- Produces, gebruikt door Task 2, 3 en 5:
  - `WEEKDAGEN: dict[str, int]` — `{"maandag": 0, …, "zondag": 6}`
  - `MIN_VOORUIT_DAGEN: int` = 3
  - `weekdag_nummer(naam: str) -> int` — raises `ValueError` bij onbekende naam
  - `parse_datum(s: str) -> datetime.date` — raises `ValueError` bij ongeldig formaat
  - `tijd_slug(tijd: str) -> str` — `"20:00"` → `"2000"`
  - `wachtrij_pad(gebruiker: str, datum: str, tijd: str) -> str`
  - `is_verlopen(datum: str, vandaag: datetime.date) -> bool`
  - `komende_weekdagen(weekdag: int, van: date, tot: date) -> list[date]`
  - `generatie_venster(gegenereerd_tot: str | None, vandaag: date, weken: int = 4) -> tuple[date, date]`

- [ ] **Step 1: Maak de tests-package aan**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 2: Schrijf de falende tests**

Maak `tests/test_wachtrij_regels.py` met exact deze inhoud:

```python
import unittest
from datetime import date

from wachtrij_regels import (
    weekdag_nummer,
    parse_datum,
    tijd_slug,
    wachtrij_pad,
    is_verlopen,
    komende_weekdagen,
    generatie_venster,
)


class TestWeekdagNummer(unittest.TestCase):
    def test_maandag_is_nul(self):
        self.assertEqual(weekdag_nummer("maandag"), 0)

    def test_dinsdag_is_een(self):
        self.assertEqual(weekdag_nummer("dinsdag"), 1)

    def test_zondag_is_zes(self):
        self.assertEqual(weekdag_nummer("zondag"), 6)

    def test_hoofdletters_en_spaties_worden_genegeerd(self):
        self.assertEqual(weekdag_nummer("  Dinsdag "), 1)

    def test_onbekende_weekdag_faalt(self):
        with self.assertRaises(ValueError):
            weekdag_nummer("dinsdagavond")


class TestParseDatum(unittest.TestCase):
    def test_geldige_datum(self):
        self.assertEqual(parse_datum("2026-08-11"), date(2026, 8, 11))

    def test_ongeldig_formaat_faalt(self):
        with self.assertRaises(ValueError):
            parse_datum("11-08-2026")


class TestTijdSlug(unittest.TestCase):
    def test_dubbele_punt_verdwijnt(self):
        self.assertEqual(tijd_slug("20:00"), "2000")

    def test_ochtendtijd(self):
        self.assertEqual(tijd_slug("09:30"), "0930")


class TestWachtrijPad(unittest.TestCase):
    def test_pad_gebruikt_forward_slashes(self):
        self.assertEqual(
            wachtrij_pad("toine_aanraad", "2026-08-11", "20:00"),
            "wachtrij/toine_aanraad/2026-08-11_2000.json",
        )


class TestIsVerlopen(unittest.TestCase):
    def test_gisteren_is_verlopen(self):
        self.assertTrue(is_verlopen("2026-08-06", date(2026, 8, 7)))

    def test_vandaag_is_niet_verlopen(self):
        self.assertFalse(is_verlopen("2026-08-07", date(2026, 8, 7)))

    def test_morgen_is_niet_verlopen(self):
        self.assertFalse(is_verlopen("2026-08-08", date(2026, 8, 7)))

    def test_onleesbare_datum_is_niet_verlopen(self):
        # Liever een item laten staan dan data weggooien op een parse-fout.
        self.assertFalse(is_verlopen("kapot", date(2026, 8, 7)))


class TestKomendeWeekdagen(unittest.TestCase):
    def test_dinsdagen_binnen_venster(self):
        # 2026-08-07 is een vrijdag; dinsdagen zijn 11, 18, 25 augustus.
        self.assertEqual(
            komende_weekdagen(1, date(2026, 8, 7), date(2026, 8, 26)),
            [date(2026, 8, 11), date(2026, 8, 18), date(2026, 8, 25)],
        )

    def test_ondergrens_is_inclusief(self):
        self.assertEqual(
            komende_weekdagen(1, date(2026, 8, 11), date(2026, 8, 11)),
            [date(2026, 8, 11)],
        )

    def test_bovengrens_is_inclusief(self):
        self.assertIn(
            date(2026, 8, 18),
            komende_weekdagen(1, date(2026, 8, 12), date(2026, 8, 18)),
        )

    def test_loopt_over_maandgrens(self):
        self.assertEqual(
            komende_weekdagen(1, date(2026, 8, 27), date(2026, 9, 9)),
            [date(2026, 9, 1), date(2026, 9, 8)],
        )

    def test_loopt_over_jaargrens(self):
        self.assertEqual(
            komende_weekdagen(1, date(2026, 12, 28), date(2027, 1, 6)),
            [date(2026, 12, 29), date(2027, 1, 5)],
        )

    def test_leeg_venster(self):
        self.assertEqual(
            komende_weekdagen(1, date(2026, 8, 20), date(2026, 8, 19)), []
        )


class TestGeneratieVenster(unittest.TestCase):
    def test_zonder_watermark_start_drie_dagen_vooruit(self):
        van, tot = generatie_venster(None, date(2026, 8, 7), weken=4)
        self.assertEqual(van, date(2026, 8, 10))
        self.assertEqual(tot, date(2026, 9, 4))

    def test_watermark_in_de_toekomst_verschuift_ondergrens(self):
        van, _ = generatie_venster("2026-08-18", date(2026, 8, 7), weken=4)
        self.assertEqual(van, date(2026, 8, 19))

    def test_watermark_ver_in_verleden_levert_geen_datums_uit_verleden(self):
        # Regel stond maanden op actief:false. De ondergrens moet vandaag+3
        # blijven, niet terugvallen op de oude watermark.
        van, _ = generatie_venster("2026-01-05", date(2026, 8, 7), weken=4)
        self.assertEqual(van, date(2026, 8, 10))

    def test_watermark_gisteren_levert_nog_steeds_vandaag_plus_drie(self):
        van, _ = generatie_venster("2026-08-06", date(2026, 8, 7), weken=4)
        self.assertEqual(van, date(2026, 8, 10))
```

- [ ] **Step 3: Draai de tests en bevestig dat ze falen**

Run: `python -m unittest tests.test_wachtrij_regels -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wachtrij_regels'`

- [ ] **Step 4: Schrijf de implementatie**

Maak `wachtrij_regels.py` met exact deze inhoud:

```python
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
```

- [ ] **Step 5: Draai de tests en bevestig dat ze slagen**

Run: `python -m unittest tests.test_wachtrij_regels -v`
Expected: PASS — `Ran 24 tests`, `OK`

- [ ] **Step 6: Commit**

```bash
git add wachtrij_regels.py tests/__init__.py tests/test_wachtrij_regels.py
git commit -m "feat: dependency-vrije datumlogica voor wachtrij-items"
```

---

### Task 2: Validatie van herhaalregels

**Files:**
- Create: `genereer_herhalingen.py`
- Create: `tests/test_genereer_herhalingen.py`

**Interfaces:**
- Consumes uit Task 1: `weekdag_nummer(naam) -> int`.
- Produces, gebruikt door Task 3 en 4:
  - `valideer_regels(regels: list[dict], gebruikers: list[dict], leden_namen: set[str]) -> list[str]` — retourneert een lijst foutmeldingen; leeg betekent geldig. Krijgt **alleen actieve regels** aangeleverd.

- [ ] **Step 1: Schrijf de falende tests**

Maak `tests/test_genereer_herhalingen.py` met exact deze inhoud:

```python
import unittest

from genereer_herhalingen import valideer_regels

GEBRUIKERS = [
    {"id": "joris_van_den_broek", "naam": "Joris van den Broek"},
    {"id": "toine_aanraad", "naam": "Toine Aanraad"},
    {"id": "chris_van_waardenburg", "naam": "Chris van Waardenburg"},
]

LEDEN = {
    "Joris van den Broek",
    "Toine Aanraad",
    "Chris van Waardenburg",
    "Peter Nijhof",
    "Jan Verhoeven",
    "Herman Brugmans",
    "Ellen Daniels",
}


def regel(**overrides):
    basis = {
        "id": "dinsdag-padel-joris",
        "actief": True,
        "weekdag": "dinsdag",
        "tijd": "20:00",
        "sport": "padel",
        "gebruiker": "joris_van_den_broek",
        "spelers": [
            "Joris van den Broek",
            "Peter Nijhof",
            "Jan Verhoeven",
            "Herman Brugmans",
        ],
    }
    basis.update(overrides)
    return basis


class TestValideerRegels(unittest.TestCase):
    def test_geldige_regel_geeft_geen_fouten(self):
        self.assertEqual(valideer_regels([regel()], GEBRUIKERS, LEDEN), [])

    def test_onbekende_gebruiker(self):
        fouten = valideer_regels([regel(gebruiker="niemand")], GEBRUIKERS, LEDEN)
        self.assertTrue(any("niemand" in f for f in fouten))

    def test_onbekende_weekdag(self):
        fouten = valideer_regels([regel(weekdag="dinsdagavond")], GEBRUIKERS, LEDEN)
        self.assertTrue(any("weekdag" in f for f in fouten))

    def test_ongeldige_sport(self):
        fouten = valideer_regels([regel(sport="squash")], GEBRUIKERS, LEDEN)
        self.assertTrue(any("sport" in f for f in fouten))

    def test_ongeldige_tijd(self):
        fouten = valideer_regels([regel(tijd="8 uur")], GEBRUIKERS, LEDEN)
        self.assertTrue(any("tijd" in f for f in fouten))

    def test_te_weinig_spelers(self):
        fouten = valideer_regels(
            [regel(spelers=["Joris van den Broek", "Peter Nijhof"])],
            GEBRUIKERS,
            LEDEN,
        )
        self.assertTrue(any("4 spelers" in f for f in fouten))

    def test_boeker_niet_op_positie_nul(self):
        fouten = valideer_regels(
            [
                regel(
                    spelers=[
                        "Peter Nijhof",
                        "Joris van den Broek",
                        "Jan Verhoeven",
                        "Herman Brugmans",
                    ]
                )
            ],
            GEBRUIKERS,
            LEDEN,
        )
        self.assertTrue(any("boeker" in f for f in fouten))

    def test_speler_niet_in_ledenlijst(self):
        fouten = valideer_regels(
            [
                regel(
                    spelers=[
                        "Joris van den Broek",
                        "Peter Nijhof",
                        "Jan Verhoeven",
                        "Typfout Naam",
                    ]
                )
            ],
            GEBRUIKERS,
            LEDEN,
        )
        self.assertTrue(any("Typfout Naam" in f for f in fouten))

    def test_dezelfde_speler_in_twee_regels_op_dezelfde_weekdag(self):
        eerste = regel(id="dinsdag-padel-joris")
        tweede = regel(
            id="dinsdag-padel-toine",
            gebruiker="toine_aanraad",
            spelers=[
                "Toine Aanraad",
                "Peter Nijhof",  # zit ook al in de eerste regel
                "Ellen Daniels",
                "Chris van Waardenburg",
            ],
        )
        fouten = valideer_regels([eerste, tweede], GEBRUIKERS, LEDEN)
        self.assertTrue(any("Peter Nijhof" in f for f in fouten))

    def test_dezelfde_speler_op_verschillende_weekdagen_mag(self):
        eerste = regel(id="dinsdag-padel-joris")
        tweede = regel(
            id="donderdag-padel-toine",
            weekdag="donderdag",
            gebruiker="toine_aanraad",
            spelers=[
                "Toine Aanraad",
                "Peter Nijhof",
                "Ellen Daniels",
                "Chris van Waardenburg",
            ],
        )
        self.assertEqual(valideer_regels([eerste, tweede], GEBRUIKERS, LEDEN), [])

    def test_meerdere_fouten_worden_allemaal_gemeld(self):
        fouten = valideer_regels(
            [regel(sport="squash", tijd="8 uur")], GEBRUIKERS, LEDEN
        )
        self.assertGreaterEqual(len(fouten), 2)
```

- [ ] **Step 2: Draai de tests en bevestig dat ze falen**

Run: `python -m unittest tests.test_genereer_herhalingen -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'genereer_herhalingen'`

- [ ] **Step 3: Schrijf de implementatie**

Maak `genereer_herhalingen.py` met exact deze inhoud:

```python
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
```

- [ ] **Step 4: Draai de tests en bevestig dat ze slagen**

Run: `python -m unittest tests.test_genereer_herhalingen -v`
Expected: PASS — `Ran 11 tests`, `OK`

- [ ] **Step 5: Commit**

```bash
git add genereer_herhalingen.py tests/test_genereer_herhalingen.py
git commit -m "feat: validatie van herhaalregels"
```

---

### Task 3: Generatorkern `plan_items`

**Files:**
- Modify: `genereer_herhalingen.py` (functies toevoegen onder `valideer_regels`)
- Modify: `tests/test_genereer_herhalingen.py` (testklassen toevoegen)

**Interfaces:**
- Consumes uit Task 1: `weekdag_nummer`, `komende_weekdagen`, `generatie_venster`, `wachtrij_pad`.
- Produces, gebruikt door Task 4:
  - `maak_item(regel: dict, datum: str, ingediend: str) -> dict`
  - `plan_items(regels: list[dict], vandaag: date, bestaat, ingediend: str, weken: int = 4) -> tuple[list[tuple[str, dict]], list[dict]]` — retourneert `(nieuwe_items, bijgewerkte_regels)`. `bestaat` is een callable `(pad: str) -> bool`, geïnjecteerd zodat tests het bestandssysteem niet raken.

- [ ] **Step 1: Schrijf de falende tests**

Voeg bovenaan `tests/test_genereer_herhalingen.py` toe aan de bestaande imports:

```python
from datetime import date

from genereer_herhalingen import maak_item, plan_items, valideer_regels
```

(vervang daarmee de bestaande `from genereer_herhalingen import valideer_regels`)

Voeg onderaan hetzelfde bestand toe:

```python
NOOIT = lambda pad: False  # noqa: E731 - niets bestaat al
ALTIJD = lambda pad: True  # noqa: E731 - alles bestaat al


class TestMaakItem(unittest.TestCase):
    def test_itemformaat_komt_overeen_met_bestaande_wachtrij_items(self):
        item = maak_item(regel(), "2026-08-11", "2026-08-07T12:00:00")
        self.assertEqual(
            item,
            {
                "gebruiker": "joris_van_den_broek",
                "datum": "2026-08-11",
                "tijd": "20:00",
                "sport": "padel",
                "spelers": [
                    "Joris van den Broek",
                    "Peter Nijhof",
                    "Jan Verhoeven",
                    "Herman Brugmans",
                ],
                "ingediend": "2026-08-07T12:00:00",
            },
        )

    def test_spelerslijst_is_een_kopie(self):
        bron = regel()
        item = maak_item(bron, "2026-08-11", "nu")
        item["spelers"].append("Indringer")
        self.assertEqual(len(bron["spelers"]), 4)


class TestPlanItems(unittest.TestCase):
    def test_genereert_dinsdagen_binnen_vier_weken(self):
        nieuwe, _ = plan_items([regel()], date(2026, 8, 7), NOOIT, "nu")
        datums = [item["datum"] for _, item in nieuwe]
        self.assertEqual(
            datums, ["2026-08-11", "2026-08-18", "2026-08-25", "2026-09-01"]
        )

    def test_paden_kloppen(self):
        nieuwe, _ = plan_items([regel()], date(2026, 8, 7), NOOIT, "nu")
        self.assertEqual(
            nieuwe[0][0], "wachtrij/joris_van_den_broek/2026-08-11_2000.json"
        )

    def test_watermark_schuift_op_naar_laatste_datum(self):
        _, bijgewerkt = plan_items([regel()], date(2026, 8, 7), NOOIT, "nu")
        self.assertEqual(bijgewerkt[0]["gegenereerd_tot"], "2026-09-01")

    def test_bestaand_bestand_wordt_niet_opnieuw_aangemaakt(self):
        nieuwe, _ = plan_items([regel()], date(2026, 8, 7), ALTIJD, "nu")
        self.assertEqual(nieuwe, [])

    def test_watermark_schuift_ook_op_als_alles_al_bestond(self):
        _, bijgewerkt = plan_items([regel()], date(2026, 8, 7), ALTIJD, "nu")
        self.assertEqual(bijgewerkt[0]["gegenereerd_tot"], "2026-09-01")

    def test_verwijderd_item_komt_niet_terug(self):
        # Eerste run genereert t/m 2026-09-01. Daarna verwijdert de gebruiker
        # het item van 18 augustus. Een tweede run op dezelfde dag mag dat
        # item niet opnieuw aanmaken, want het ligt achter de watermark.
        _, na_eerste = plan_items([regel()], date(2026, 8, 7), NOOIT, "nu")
        nieuwe, _ = plan_items(na_eerste, date(2026, 8, 7), NOOIT, "nu")
        self.assertEqual(nieuwe, [])

    def test_inactieve_regel_genereert_niets_en_houdt_watermark(self):
        inactief = regel(actief=False, gegenereerd_tot="2026-08-11")
        nieuwe, bijgewerkt = plan_items([inactief], date(2026, 8, 7), NOOIT, "nu")
        self.assertEqual(nieuwe, [])
        self.assertEqual(bijgewerkt[0]["gegenereerd_tot"], "2026-08-11")

    def test_oorspronkelijke_regel_wordt_niet_gemuteerd(self):
        bron = regel()
        plan_items([bron], date(2026, 8, 7), NOOIT, "nu")
        self.assertNotIn("gegenereerd_tot", bron)

    def test_meerdere_regels_leveren_items_per_gebruiker(self):
        tweede = regel(
            id="dinsdag-tennis-chris",
            sport="tennis",
            gebruiker="chris_van_waardenburg",
            spelers=[
                "Chris van Waardenburg",
                "Ellen Daniels",
                "Toine Aanraad",
                "Jan Verhoeven",
            ],
        )
        nieuwe, _ = plan_items([regel(), tweede], date(2026, 8, 7), NOOIT, "nu")
        paden = [pad for pad, _ in nieuwe]
        self.assertTrue(
            any(p.startswith("wachtrij/joris_van_den_broek/") for p in paden)
        )
        self.assertTrue(
            any(p.startswith("wachtrij/chris_van_waardenburg/") for p in paden)
        )
```

- [ ] **Step 2: Draai de tests en bevestig dat ze falen**

Run: `python -m unittest tests.test_genereer_herhalingen -v`
Expected: FAIL — `ImportError: cannot import name 'maak_item' from 'genereer_herhalingen'`

- [ ] **Step 3: Schrijf de implementatie**

Vervang in `genereer_herhalingen.py` de importregel

```python
from wachtrij_regels import weekdag_nummer
```

door

```python
from wachtrij_regels import (
    generatie_venster,
    komende_weekdagen,
    wachtrij_pad,
    weekdag_nummer,
)
```

en voeg onderaan het bestand toe:

```python
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
```

- [ ] **Step 4: Draai de tests en bevestig dat ze slagen**

Run: `python -m unittest tests.test_genereer_herhalingen -v`
Expected: PASS — `Ran 22 tests`, `OK`

- [ ] **Step 5: Commit**

```bash
git add genereer_herhalingen.py tests/test_genereer_herhalingen.py
git commit -m "feat: generatorkern die wachtrij-items uit herhaalregels plant"
```

---

### Task 4: CLI-laag, `herhalingen.json` en workflow

**Files:**
- Modify: `genereer_herhalingen.py` (imports uitbreiden, `main()` toevoegen)
- Create: `herhalingen.json`
- Create: `.github/workflows/genereer_herhalingen.yml`

**Interfaces:**
- Consumes uit Task 2 en 3: `valideer_regels`, `plan_items`.
- Produces: uitvoerbaar script `python genereer_herhalingen.py` (exit 1 bij validatiefouten, exit 0 bij succes).

**Let op:** de 12 spelersnamen zijn nog niet bekend (zie "Openstaand voor implementatie" in de spec). Vul in Step 2 de placeholders in met de echte namen zoals ze in `leden.json` staan. Zonder echte namen faalt de validatie op "staat niet in leden.json" — dat is bedoeld gedrag, geen bug.

- [ ] **Step 1: Breid de imports uit en voeg `main()` toe**

Vervang bovenin `genereer_herhalingen.py`

```python
import re
```

door

```python
import json
import logging
import os
import re
import sys
from datetime import date, datetime
```

en voeg direct onder de `GELDIGE_SPORTEN`-regel toe:

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

HERHALINGEN_FILE = "herhalingen.json"
GEBRUIKERS_FILE = "gebruikers.json"
LEDEN_FILE = "leden.json"
```

Voeg onderaan het bestand toe:

```python
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
```

- [ ] **Step 2: Maak `herhalingen.json`**

Vervang elke `VUL_NAAM_IN` door een echte naam uit `leden.json`:

```json
[
  {
    "id": "dinsdag-tennis-chris",
    "actief": true,
    "weekdag": "dinsdag",
    "tijd": "20:00",
    "sport": "tennis",
    "gebruiker": "chris_van_waardenburg",
    "spelers": [
      "Chris van Waardenburg",
      "VUL_NAAM_IN",
      "VUL_NAAM_IN",
      "VUL_NAAM_IN"
    ]
  },
  {
    "id": "dinsdag-padel-toine",
    "actief": true,
    "weekdag": "dinsdag",
    "tijd": "20:00",
    "sport": "padel",
    "gebruiker": "toine_aanraad",
    "spelers": [
      "Toine Aanraad",
      "VUL_NAAM_IN",
      "VUL_NAAM_IN",
      "VUL_NAAM_IN"
    ]
  },
  {
    "id": "dinsdag-padel-joris",
    "actief": true,
    "weekdag": "dinsdag",
    "tijd": "20:00",
    "sport": "padel",
    "gebruiker": "joris_van_den_broek",
    "spelers": [
      "Joris van den Broek",
      "VUL_NAAM_IN",
      "VUL_NAAM_IN",
      "VUL_NAAM_IN"
    ]
  }
]
```

`gegenereerd_tot` ontbreekt bewust — de eerste run vult hem.

- [ ] **Step 3: Draai de validatie lokaal en bevestig dat hij faalt op onbekende namen**

Run: `python genereer_herhalingen.py`
Expected: FAIL met exit 1 en regels als `dinsdag-tennis-chris: speler 'VUL_NAAM_IN' staat niet in leden.json`

Dit bevestigt dat de validatie werkt vóórdat er items worden aangemaakt. Vul daarna de echte namen in.

- [ ] **Step 4: Draai opnieuw met echte namen en controleer het resultaat**

Run: `python genereer_herhalingen.py`
Expected: PASS — regels `Aangemaakt: wachtrij/<gebruiker>/<datum>_2000.json` en tot slot `9 nieuw(e) wachtrij-item(s) aangemaakt` of `12 …`.

Het venster is `[vandaag+3, vandaag+28]`, dus 26 dagen breed; daar vallen 3 óf 4 dinsdagen in, afhankelijk van de dag waarop je draait. Bij 3 regels is het resultaat dus 9 of 12 items — beide correct. Controleer dat het aantal een veelvoud van 3 is.

Controleer daarna dat een item het juiste formaat heeft:

```bash
cat wachtrij/joris_van_den_broek/*_2000.json | head -20
git diff herhalingen.json
```

Expected: `gegenereerd_tot` staat nu in alle drie de regels.

- [ ] **Step 5: Draai nogmaals en bevestig idempotentie**

Run: `python genereer_herhalingen.py`
Expected: `0 nieuw(e) wachtrij-item(s) aangemaakt`

- [ ] **Step 6: Maak de workflow**

Maak `.github/workflows/genereer_herhalingen.yml` met exact deze inhoud:

```yaml
name: Genereer herhalingen

# Maakt wachtrij-items aan uit herhalingen.json. Bewust NIET tijdkritisch --
# het venster is dagen breed, dus GitHub's eigen cron volstaat hier en
# cron-job.org is niet nodig (anders dan bij de 07:00-boeking).

on:
  workflow_dispatch:
  schedule:
    - cron: '0 4 * * 1'  # maandag 06:00 NL (CEST) / 05:00 (CET)

permissions:
  contents: write

concurrency:
  group: knltb-genereer-herhalingen
  cancel-in-progress: false

jobs:
  genereer:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    env:
      TZ: Europe/Amsterdam
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      # Geen pip install: genereer_herhalingen.py gebruikt alleen stdlib.
      - name: Genereer wachtrij-items
        run: python genereer_herhalingen.py

      - name: Commit en push
        run: |
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git config user.name  "knltb-autoboek-bot"
          git add herhalingen.json wachtrij/
          git diff --cached --quiet && echo "Niets te committen" && exit 0
          git commit -m "herhalingen: wachtrij-items gegenereerd"
          for i in 1 2 3 4 5; do
            git pull --rebase --autostash origin main && git push && break
            echo "Push poging $i mislukt, retry..."
            sleep $i
          done
```

- [ ] **Step 7: Commit**

```bash
git add genereer_herhalingen.py herhalingen.json .github/workflows/genereer_herhalingen.yml wachtrij/
git commit -m "feat: generator-CLI, herhaalregels en wekelijkse workflow"
```

---

### Task 5: Vervaltermijn in `ruim_wachtrij_op()`

**Files:**
- Modify: `lees_reserveringen.py:24` (import uitbreiden), `lees_reserveringen.py:943-981` (functie)
- Create: `tests/test_ruim_wachtrij.py`

**Interfaces:**
- Consumes uit Task 1: `is_verlopen(datum, vandaag) -> bool`.
- Produces: geen nieuwe publieke functie; `ruim_wachtrij_op()` verwijdert voortaan ook items met een verstreken speeldatum.

**Let op:** `lees_reserveringen.py` importeert selenium op moduleniveau en is daardoor lokaal niet importeerbaar. De test dekt daarom de beslisregel via `is_verlopen` uit Task 1 plus een expliciete controle op de volgorde binnen de functie. Draai `python -m unittest` vanaf de repo-root.

- [ ] **Step 1: Schrijf de falende test**

Maak `tests/test_ruim_wachtrij.py` met exact deze inhoud:

```python
"""
lees_reserveringen.py importeert selenium op moduleniveau en is lokaal niet
importeerbaar. Deze test dekt daarom (a) de beslisregel zelf via is_verlopen en
(b) dat ruim_wachtrij_op() die regel toepast vóór de match-op-reservering, door
de brontekst te controleren.
"""

import re
import unittest
from datetime import date
from pathlib import Path

from wachtrij_regels import is_verlopen

BRON = Path(__file__).resolve().parent.parent / "lees_reserveringen.py"


class TestBeslisregel(unittest.TestCase):
    def test_verstreken_speeldatum(self):
        self.assertTrue(is_verlopen("2026-08-06", date(2026, 8, 7)))

    def test_speeldatum_vandaag_blijft_staan(self):
        self.assertFalse(is_verlopen("2026-08-07", date(2026, 8, 7)))

    def test_toekomstige_speeldatum_blijft_staan(self):
        self.assertFalse(is_verlopen("2026-08-11", date(2026, 8, 7)))


class TestRuimWachtrijOp(unittest.TestCase):
    def setUp(self):
        self.bron = BRON.read_text(encoding="utf-8")
        start = self.bron.index("def ruim_wachtrij_op")
        eind = self.bron.index("\ndef ", start + 1)
        self.functie = self.bron[start:eind]

    def test_module_importeert_is_verlopen(self):
        self.assertRegex(
            self.bron, r"from wachtrij_regels import[^\n]*is_verlopen"
        )

    def test_functie_gebruikt_is_verlopen(self):
        self.assertIn("is_verlopen(", self.functie)

    def test_vervalcheck_staat_voor_de_match_op_reserveringen(self):
        # De verstreken-check moet vóór de spelers-match komen, anders kost
        # elke verlopen item nog een volledige vergelijkingslus.
        self.assertLess(
            self.functie.index("is_verlopen("),
            self.functie.index("wachtrij_spelers"),
        )

    def test_verlopen_item_wordt_verwijderd_en_geteld(self):
        segment = self.functie[self.functie.index("is_verlopen(") :]
        segment = segment[: segment.index("wachtrij_spelers")]
        self.assertIn("os.remove(f)", segment)
        self.assertIn("verwijderd.append(f)", segment)
        self.assertIn("continue", segment)
```

- [ ] **Step 2: Draai de test en bevestig dat hij faalt**

Run: `python -m unittest tests.test_ruim_wachtrij -v`
Expected: FAIL — `test_module_importeert_is_verlopen` en `test_functie_gebruikt_is_verlopen` falen; de drie `TestBeslisregel`-tests slagen al.

- [ ] **Step 3: Voeg de import toe**

In `lees_reserveringen.py`, vervang regel 24:

```python
from datetime import datetime
```

door:

```python
from datetime import date, datetime

from wachtrij_regels import is_verlopen
```

- [ ] **Step 4: Voeg de vervalcheck toe aan `ruim_wachtrij_op()`**

In `lees_reserveringen.py`, in `ruim_wachtrij_op()`, vervang dit blok:

```python
        datum = item.get('datum', '')
        tijd  = item.get('tijd', '')
        if not datum or not tijd:
            continue
        wachtrij_spelers = set(item.get('spelers', []))
```

door:

```python
        datum = item.get('datum', '')
        tijd  = item.get('tijd', '')
        if not datum or not tijd:
            continue
        # Speeldatum voorbij: opruimen ongeacht of er een reservering matcht.
        # Anders blijft een mislukte boeking eeuwig als rode kruis in de PWA
        # staan, want de match-op-reservering vindt dan nooit iets.
        if is_verlopen(datum, date.today()):
            os.remove(f)
            verwijderd.append(f)
            log.info(f"Wachtrij opgeruimd: {f} (speeldatum {datum} is voorbij)")
            continue
        wachtrij_spelers = set(item.get('spelers', []))
```

Werk ook de docstring van de functie bij: vervang

```python
    Verwijder wachtrij-items waarvan datum + spelers overeenkomen met een
    gescrapete reservering -- de boeking is kennelijk geslaagd.
```

door

```python
    Verwijder wachtrij-items die (a) een verstreken speeldatum hebben, of
    (b) waarvan datum + spelers overeenkomen met een gescrapete reservering
    -- de boeking is dan kennelijk geslaagd.
```

- [ ] **Step 5: Draai de test en bevestig dat hij slaagt**

Run: `python -m unittest tests.test_ruim_wachtrij -v`
Expected: PASS — `Ran 7 tests`, `OK`

- [ ] **Step 6: Draai de hele suite**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS — `OK`, geen failures of errors.

- [ ] **Step 7: Commit**

```bash
git add lees_reserveringen.py tests/test_ruim_wachtrij.py
git commit -m "feat: ruim wachtrij-items met verstreken speeldatum op"
```

---

### Task 6: Documentatie bijwerken

**Files:**
- Modify: `README.md` (bestandstabel rond regel 45-63; nieuwe sectie na "Multi-user setup")
- Modify: `knltb-autoboek.md` (nieuwe subsectie over herhalingen)

**Interfaces:**
- Consumes: alle voorgaande taken (namen van bestanden en workflows).
- Produces: geen code.

- [ ] **Step 1: Vul de bestandstabel in `README.md` aan**

Voeg onder de regel voor `gebruikers.json` toe:

```markdown
| `herhalingen.json` | Wekelijks terugkerende reserveringen (weekdag, tijd, sport, boeker, 4 spelers). `gegenereerd_tot` wordt door de generator beheerd |
| `genereer_herhalingen.py` | Maakt wachtrij-items aan uit `herhalingen.json` -- alleen stdlib, geen dependencies |
| `wachtrij_regels.py` | Gedeelde datum- en padlogica rond wachtrij-items (gebruikt door de generator en `lees_reserveringen.py`) |
```

Voeg onder de regel voor `publiceer_pwa.yml` toe:

```markdown
| `.github/workflows/genereer_herhalingen.yml` | Genereert wekelijks (maandag 06:00 NL) wachtrij-items uit `herhalingen.json` |
```

- [ ] **Step 2: Voeg een sectie toe aan `README.md`**

Voeg direct na de sectie "Multi-user setup" (dus vóór de `---` die erop volgt) toe:

```markdown
---

## Terugkerende reserveringen

`herhalingen.json` beschrijft reserveringen die elke week terugkomen. Elke
maandagochtend maakt `genereer_herhalingen.yml` daaruit wachtrij-items aan voor
de komende 4 weken; daarna verloopt alles via de normale wachtrij-flow.

```json
[
  {
    "id": "dinsdag-padel-joris",
    "actief": true,
    "weekdag": "dinsdag",
    "tijd": "20:00",
    "sport": "padel",
    "gebruiker": "joris_van_den_broek",
    "spelers": ["Joris van den Broek", "…", "…", "…"],
    "gegenereerd_tot": "2026-09-01"
  }
]
```

`spelers[0]` is altijd de boeker zelf, met exact de naam uit `gebruikers.json`.
`gegenereerd_tot` wordt door de generator beheerd -- niet met de hand aanpassen,
behalve om bewust opnieuw te laten genereren.

### Bediening

| Wat | Hoe |
|-----|-----|
| Eén week overslaan | 🗑️ op het geplande item in de PWA. Komt niet terug: de generator kijkt nooit vóór `gegenereerd_tot` |
| Langer stoppen | `actief: false` op de regel. Stopt nieuwe generatie, laat ingeplande items staan |
| Spelers wijzigen | Pas `spelers` aan. Geldt vanaf de eerstvolgende generatie; al ingeplande items houden de oude namen |
| Opnieuw genereren | `gegenereerd_tot` terugzetten en de workflow handmatig draaien |

### Validatie

De generator controleert vóór hij iets schrijft, en faalt hard bij een fout:
gebruiker moet in `gebruikers.json` staan, alle 4 spelersnamen letterlijk in
`leden.json`, `spelers[0]` moet de boeker zijn, sport `padel` of `tennis`, tijd
`HH:MM`, en geen speler mag in twee regels op dezelfde weekdag voorkomen (ETV
staat geen 2e actieve reservering per lid toe -- zie `knltb-autoboek.md` 13.9).

### Let op

Een vaste wekelijkse reservering legt beslag op de enige reserveringsplek van
alle betrokken spelers, van de boekdag (speeldatum -2) tot de speeldatum zelf.
Wie in dat venster iets anders wil boeken, botst daarop.
```

- [ ] **Step 3: Voeg een subsectie toe aan `knltb-autoboek.md`**

Voeg toe aan sectie 13 (Technische valkuilen en beslissingen), direct na 13.10:

```markdown
### 13.11 Watermark voorkomt dat verwijderde herhaal-items terugkomen

`genereer_herhalingen.py` houdt per regel een `gegenereerd_tot` bij en genereert
uitsluitend data ná die watermark. Zonder dat mechanisme zou de generator elke
week alle handmatig verwijderde items keurig terugzetten, en kun je nooit een
week overslaan.

De bestaandheidscheck op het bestandspad is *niet* wat verwijderen respecteert
-- die vangt alleen dubbele runs binnen hetzelfde venster op.

De ondergrens van het generatievenster is `max(gegenereerd_tot + 1, vandaag + 3)`.
De `vandaag + 3` is nodig omdat `verwerk_wachtrij.yml` een item oppikt op
speeldatum -2 om 06:50: een item voor overmorgen kan die trigger al gemist
hebben en zou dan onaangeraakt blijven staan tot het vervalt. De watermark-tak
is nodig omdat een regel die lang op `actief: false` stond anders data in het
verleden zou opleveren.

### 13.12 Wachtrij-items vervallen na de speeldatum

`ruim_wachtrij_op()` ruimde oorspronkelijk alleen items op die matchten met een
gescrapete reservering. Faalde een boeking, dan bleef het bestand eeuwig staan
en toonde de PWA het permanent als rode ❌. Sinds 2026-08 verwijdert de functie
ook items waarvan de speeldatum voorbij is.

De ❌ blijft daarmee zichtbaar van de boekdag (speeldatum -2) tot en met de
speeldatum zelf -- precies het venster waarin je nog handmatig een baan kunt
zoeken. De GitHub-issue die `boek.yml` bij een mislukking opent blijft als
vangnet staan.
```

- [ ] **Step 4: Commit**

```bash
git add README.md knltb-autoboek.md
git commit -m "docs: terugkerende reserveringen en wachtrij-vervaltermijn"
```

---

## Verificatie na afloop

- [ ] **Volledige testsuite**

Run: `python -m unittest discover -s tests -t . -v`
Expected: `OK`, geen failures of errors.

- [ ] **End-to-end met dry-run**

Zet tijdelijk een extra regel in `herhalingen.json` met een weekdag die over
3 dagen valt, draai `python genereer_herhalingen.py`, en controleer dat er een
wachtrij-item verschijnt. Trigger daarna handmatig:

```bash
gh workflow run verwerk_wachtrij.yml
```

Controleer in de Actions-log dat `boek.yml` gedispatcht wordt voor het juiste
item. Verwijder daarna de tijdelijke regel en het item weer.

Wil je de hele keten inclusief ETV-login testen zonder echte reservering, draai
`boek.yml` dan los met `dry_run=true`.

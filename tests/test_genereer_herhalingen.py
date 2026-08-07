import unittest
from datetime import date

from genereer_herhalingen import maak_item, plan_items, valideer_regels

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

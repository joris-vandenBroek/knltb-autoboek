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

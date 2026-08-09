import unittest
from datetime import datetime

from boek_regels import (
    PADEL_BANEN,
    TENNIS_BANEN,
    banen_voor_sport,
    baan_uit_body,
    dag_selectie_actie,
    baan_voorkeur,
    wizard_ververs_moment,
)


class TestWizardVerversMoment(unittest.TestCase):
    """
    De wizard staat vanaf ~06:52 idle op ReservationsDay te wachten op 07:00.
    Na die 8 minuten accepteerde ETV de dagdeel-submit niet meer (run #199/#200,
    09-08-2026). Door vlak voor het startsein te verversen begint de spits met
    een verse sessie in plaats van een verlopen formulier.
    """

    DOEL = datetime(2026, 8, 9, 7, 0, 1)

    def test_ruim_op_tijd_geeft_verversmoment(self):
        moment = wizard_ververs_moment(datetime(2026, 8, 9, 6, 52, 0), self.DOEL, marge_s=45)
        self.assertEqual(moment, datetime(2026, 8, 9, 6, 59, 16))

    def test_marge_bepaalt_hoe_vroeg(self):
        moment = wizard_ververs_moment(datetime(2026, 8, 9, 6, 52, 0), self.DOEL, marge_s=90)
        self.assertEqual(moment, datetime(2026, 8, 9, 6, 58, 31))

    def test_te_laat_gestart_geeft_geen_verversing(self):
        # Verversen kan ons terugsturen naar de spelerspagina; dat mag alleen
        # als er tijd is om te herstellen. Anders liever de oude wizard houden.
        self.assertIsNone(
            wizard_ververs_moment(datetime(2026, 8, 9, 6, 59, 30), self.DOEL, marge_s=45))

    def test_precies_op_het_moment_geeft_geen_verversing(self):
        self.assertIsNone(
            wizard_ververs_moment(datetime(2026, 8, 9, 6, 59, 16), self.DOEL, marge_s=45))

    def test_na_het_startsein_geeft_geen_verversing(self):
        self.assertIsNone(
            wizard_ververs_moment(datetime(2026, 8, 9, 7, 0, 30), self.DOEL, marge_s=45))


ALLE_GEBRUIKERS = ["joris_van_den_broek", "toine_aanraad", "chris_van_waardenburg"]


class TestBaanVoorkeur(unittest.TestCase):
    """
    Run #199/#200 (09-08-2026): Joris en Toine wilden allebei padel op dezelfde
    dag om 20:00 en vuurden op dezelfde seconde. De padel-sortering was oplopend,
    dus beide runs mikten gegarandeerd eerst op Padel 1 — zelfgemaakte
    concurrentie. Elk account krijgt daarom een eigen startbaan.
    """

    def test_geeft_alle_banen_terug(self):
        volgorde = baan_voorkeur("joris_van_den_broek", "padel", ALLE_GEBRUIKERS)
        self.assertEqual(sorted(volgorde), sorted(PADEL_BANEN))

    def test_is_een_rotatie_van_de_basisvolgorde(self):
        volgorde = baan_voorkeur("toine_aanraad", "padel", ALLE_GEBRUIKERS)
        start = PADEL_BANEN.index(volgorde[0])
        self.assertEqual(volgorde, PADEL_BANEN[start:] + PADEL_BANEN[:start])

    def test_accounts_starten_op_verschillende_banen(self):
        eersten = [baan_voorkeur(g, "padel", ALLE_GEBRUIKERS)[0] for g in ALLE_GEBRUIKERS]
        self.assertEqual(len(set(eersten)), len(ALLE_GEBRUIKERS),
                         f"accounts botsen nog steeds op dezelfde baan: {eersten}")

    def test_is_deterministisch(self):
        a = baan_voorkeur("joris_van_den_broek", "padel", ALLE_GEBRUIKERS)
        b = baan_voorkeur("joris_van_den_broek", "padel", ALLE_GEBRUIKERS)
        self.assertEqual(a, b)

    def test_volgorde_van_de_gebruikerslijst_maakt_niet_uit(self):
        # gebruikers.json mag herordend worden zonder dat iedereen ineens
        # een andere baan krijgt.
        a = baan_voorkeur("toine_aanraad", "padel", ALLE_GEBRUIKERS)
        b = baan_voorkeur("toine_aanraad", "padel", list(reversed(ALLE_GEBRUIKERS)))
        self.assertEqual(a, b)

    def test_onbekende_gebruiker_krijgt_geldige_volgorde(self):
        volgorde = baan_voorkeur("iemand_anders", "padel", ALLE_GEBRUIKERS)
        self.assertEqual(sorted(volgorde), sorted(PADEL_BANEN))

    def test_zonder_gebruikerslijst_valt_terug_op_basisvolgorde(self):
        self.assertEqual(baan_voorkeur("joris_van_den_broek", "padel", []), PADEL_BANEN)

    def test_tennis_houdt_hoogste_baan_eerst(self):
        # Bewust ongemoeid: baan 04 is de slechtste tennisbaan, daarom hoogste
        # eerst (commit e9a76b1). Spreiden zou dat terugdraaien.
        volgorde = baan_voorkeur("joris_van_den_broek", "tennis", ALLE_GEBRUIKERS)
        self.assertEqual(volgorde, list(reversed(TENNIS_BANEN)))

    def test_tennis_is_gelijk_voor_alle_accounts(self):
        volgordes = [baan_voorkeur(g, "tennis", ALLE_GEBRUIKERS) for g in ALLE_GEBRUIKERS]
        self.assertEqual(volgordes[0], volgordes[1])
        self.assertEqual(volgordes[1], volgordes[2])


class TestBanenVoorSport(unittest.TestCase):
    def test_padel_geeft_padelbanen(self):
        self.assertEqual(banen_voor_sport("padel"), PADEL_BANEN)

    def test_tennis_geeft_tennisbanen(self):
        self.assertEqual(banen_voor_sport("tennis"), TENNIS_BANEN)

    def test_hoofdletters_en_spaties_worden_genegeerd(self):
        self.assertEqual(banen_voor_sport("  Tennis "), TENNIS_BANEN)

    def test_onbekende_sport_valt_terug_op_padel(self):
        self.assertEqual(banen_voor_sport("squash"), PADEL_BANEN)


class TestBaanUitBody(unittest.TestCase):
    """
    Regressie voor run #198 (09-08-2026): een tennisboeking op Tennis 12 werd
    als 'Padel 3' weggeschreven omdat de verificatie altijd in PADEL_BANEN
    zocht en anders terugviel op de letterlijke string 'Padel'.
    """

    def test_padelboeking_vindt_padelbaan(self):
        self.assertEqual(baan_uit_body("Reservering Padel 3 om 20:00", "padel"), "Padel 3")

    def test_tennisboeking_vindt_tennisbaan(self):
        self.assertEqual(baan_uit_body("Reservering Tennis 12 om 20:00", "tennis"), "Tennis 12")

    def test_tennisboeking_negeert_padelbaan_van_andere_reservering(self):
        # Dit is precies de bug: de overzichtspagina toont meerdere
        # reserveringen; 'Padel 3' hoort bij een andere boeking.
        body = "Padel 3 op 09-08-2026\nTennis 12 op 11-08-2026 om 20:00"
        self.assertEqual(baan_uit_body(body, "tennis"), "Tennis 12")

    def test_verwachte_baan_wint_van_andere_banen_in_body(self):
        body = "Tennis 04 op 09-08\nTennis 12 op 11-08 om 20:00"
        self.assertEqual(baan_uit_body(body, "tennis", verwachte_baan="Tennis 12"), "Tennis 12")

    def test_verwachte_baan_wordt_genegeerd_als_hij_niet_in_body_staat(self):
        body = "Tennis 04 op 11-08 om 20:00"
        self.assertEqual(baan_uit_body(body, "tennis", verwachte_baan="Tennis 12"), "Tennis 04")

    def test_geen_baan_gevonden_geeft_lege_string(self):
        # Geen terugval meer op de kale string 'Padel'.
        self.assertEqual(baan_uit_body("Geen reserveringen gevonden", "padel"), "")

    def test_tennisboeking_zonder_tennisbaan_valt_niet_terug_op_padel(self):
        self.assertEqual(baan_uit_body("Padel 3 om 20:00", "tennis"), "")


class TestDagSelectieActie(unittest.TestCase):
    """
    Regressie voor run #199/#200 (09-08-2026): na 8 minuten idle op
    ReservationsDay accepteerde ETV de dagdeel-submit niet meer. Het script
    bleef 3 minuten op diezelfde dode wizard hameren (34 pogingen) terwijl een
    verse wizard het direct in poging 1 doet. Om 07:04 was padel uitverkocht.

    De escalatie is daarom RELATIEF aan het begin van deze wizard-poging, niet
    aan de wandklok: na een herstart moet de nieuwe wizard zijn volle budget
    krijgen in plaats van meteen opnieuw af te breken.
    """

    START = datetime(2026, 8, 9, 7, 0, 1)
    HARD_STOP = datetime(2026, 8, 9, 7, 6, 0)

    def _actie(self, nu, fase_start=None):
        return dag_selectie_actie(
            nu=nu,
            fase_start=fase_start or self.START,
            budget_s=20,
            hard_stop=self.HARD_STOP,
        )

    def test_binnen_budget_blijft_doorgaan(self):
        self.assertEqual(self._actie(datetime(2026, 8, 9, 7, 0, 15)), "doorgaan")

    def test_precies_op_budget_blijft_doorgaan(self):
        self.assertEqual(self._actie(datetime(2026, 8, 9, 7, 0, 21)), "doorgaan")

    def test_over_budget_geeft_herstart(self):
        self.assertEqual(self._actie(datetime(2026, 8, 9, 7, 0, 22)), "herstart")

    def test_oude_deadline_van_drie_minuten_wordt_niet_meer_afgewacht(self):
        # Vroeger brak hij pas om 07:03:00 af; nu al ruim daarvoor.
        self.assertEqual(self._actie(datetime(2026, 8, 9, 7, 1, 0)), "herstart")

    def test_verse_wizard_krijgt_eigen_budget_na_herstart(self):
        # Wandklok staat op 07:01:30, maar deze wizard begon net om 07:01:20.
        nu = datetime(2026, 8, 9, 7, 1, 30)
        verse_start = datetime(2026, 8, 9, 7, 1, 20)
        self.assertEqual(self._actie(nu, fase_start=verse_start), "doorgaan")

    def test_na_hard_stop_geeft_stop(self):
        nu = datetime(2026, 8, 9, 7, 6, 1)
        verse_start = datetime(2026, 8, 9, 7, 6, 0)
        self.assertEqual(self._actie(nu, fase_start=verse_start), "stop")

    def test_hard_stop_wint_van_budget(self):
        # Ook binnen het budget geldt de absolute bovengrens.
        nu = datetime(2026, 8, 9, 7, 10, 0)
        verse_start = datetime(2026, 8, 9, 7, 9, 55)
        self.assertEqual(self._actie(nu, fase_start=verse_start), "stop")


class TestReplayRun199(unittest.TestCase):
    """
    Speelt de echte cadans van run #199 (09-08-2026) af. Uit de logs: de eerste
    poging viel om 07:00:01, daarna elke ~5.4s een nieuwe mislukte poging, tot
    de oude deadline om 07:03:00 na 34 pogingen afbrak.
    """

    START = datetime(2026, 8, 9, 7, 0, 1)
    CADANS_S = 5.4

    def _poging_tijd(self, n):
        from datetime import timedelta
        return self.START + timedelta(seconds=self.CADANS_S * (n - 1))

    def test_escaleert_binnen_een_halve_minuut_ipv_na_drie_minuten(self):
        hard_stop = datetime(2026, 8, 9, 7, 6, 0)
        escalatie_bij = None
        for n in range(2, 40):
            nu = self._poging_tijd(n)
            if dag_selectie_actie(nu=nu, fase_start=self.START,
                                  budget_s=20, hard_stop=hard_stop) == "herstart":
                escalatie_bij = (n, (nu - self.START).total_seconds())
                break

        self.assertIsNotNone(escalatie_bij, "had moeten escaleren")
        poging, verstreken = escalatie_bij
        # Oud gedrag: poging 34, na 179s. Nieuw: ruim binnen 30s.
        self.assertLess(poging, 34)
        self.assertLessEqual(verstreken, 30)

    def test_oude_deadline_liet_alle_34_pogingen_doorlopen(self):
        # Bewijst dat de oude absolute deadline pas na ~3 minuten ingreep, en dat
        # onze nieuwe regel dus echt iets verandert en niet toevallig hetzelfde doet.
        oude_deadline = datetime(2026, 8, 9, 7, 3, 0)
        pogingen_onder_oude_regel = sum(
            1 for n in range(2, 40) if self._poging_tijd(n) <= oude_deadline
        )
        self.assertGreaterEqual(pogingen_onder_oude_regel, 32)


if __name__ == "__main__":
    unittest.main()

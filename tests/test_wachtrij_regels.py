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

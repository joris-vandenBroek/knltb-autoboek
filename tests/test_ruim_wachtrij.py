"""
lees_reserveringen.py importeert selenium op moduleniveau en is lokaal niet
importeerbaar. Deze test dekt daarom (a) de beslisregel zelf via is_verlopen en
(b) dat ruim_wachtrij_op() die regel toepast vóór de match-op-reservering, door
de brontekst te controleren.
"""

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
        # elk verlopen item nog een volledige vergelijkingslus.
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

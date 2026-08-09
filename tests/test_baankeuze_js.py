"""
Draait de baankeuze-JS uit boek_baan.py via node tegen een nagebouwd ETV-grid.

Die JS koos tot nu toe ongetest de baan. Commit e9a76b1 (07-08-2026) brak
daardoor onopgemerkt het herkennen van ELKE padelbaan — pas twee dagen later
zichtbaar toen twee padelboekingen faalden met "Geen padel tijdslot gevonden"
op elk tijdstip, ook op een lege ochtend.

Slaat over als node ontbreekt; op de GitHub-runners staat node standaard.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HIER)
BOEK_BAAN = os.path.join(REPO, "boek_baan.py")
HARNESS = os.path.join(HIER, "baankeuze_harness.js")

_START = 'result = driver.execute_script(r"""'
_EIND = '""", tijd, sport, baan_volgorde)'


def extraheer_js(pad: str) -> str:
    """Knip het JS-blok uit boek_baan.py, zodat we de echte code testen."""
    src = open(pad, encoding="utf-8", errors="replace").read()
    start = src.index(_START) + len(_START)
    return src[start:src.index(_EIND, start)]


class TestBaankeuzeJS(unittest.TestCase):
    def test_js_blok_is_vindbaar(self):
        # Faalt zodra iemand de aanroep herschrijft; dan moet de extractie mee.
        js = extraheer_js(BOEK_BAAN)
        self.assertIn("kandidaten.sort", js)
        self.assertIn("voorkeur.indexOf", js)

    def test_geen_naieve_span_replace_meer(self):
        # Precies de regel die padel sloopte in e9a76b1.
        js = extraheer_js(BOEK_BAAN)
        self.assertNotIn("kop.replace(span.textContent", js,
                         "replace() haalt de eerste treffer weg; bij padel is dat "
                         "de baannaam zelf. Gebruik de directe tekstnodes.")

    def test_harness_draait_schoon(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node niet beschikbaar")

        js = extraheer_js(BOEK_BAAN)
        with tempfile.TemporaryDirectory() as tmp:
            js_pad = os.path.join(tmp, "baankeuze.js")
            with open(js_pad, "w", encoding="utf-8") as f:
                f.write(js)
            uitvoer = subprocess.run([node, HARNESS, js_pad],
                                     capture_output=True, text=True)

        self.assertEqual(uitvoer.returncode, 0,
                         f"JS-harness faalde:\n{uitvoer.stdout}\n{uitvoer.stderr}")
        self.assertIn("ALLE JS-CHECKS OK", uitvoer.stdout)


if __name__ == "__main__":
    unittest.main()

---
name: project-wachtrij-cleanup
description: Hoe de wachtrij-opruiming in knltb-autoboek werkt — drie mechanismen, alle drie inmiddels geïmplementeerd.
metadata:
  node_type: memory
  type: project
  originSessionId: 4581b325-9bff-46a4-8861-7a39cd945834
  modified: 2026-08-07T10:55:12.341Z
---

Wachtrij-items worden op drie manieren opgeruimd (stand 7 aug 2026, alle drie
werkend en getest):

1. **`boek.yml`** — verwijdert het bestand na een geslaagde boeking op basis van
   `inputs.datum` + `inputs.tijd`.
2. **`ruim_wachtrij_op()` in `lees_reserveringen.py`** — draait na elke scrape
   (ook de dagelijkse cron van 07:30) en verwijdert items waarvan `datum` +
   `spelers`-subset matcht met een gescrapete reservering. Tijd wordt bewust
   genegeerd, zodat een boeking op een alternatieve tijd ook opruimt.
3. **Vervaltermijn** — dezelfde functie verwijdert items waarvan de speeldatum
   voorbij is, ongeacht of er iets matcht.

**Why (3):** zonder vervaltermijn bleef een mislukte boeking eeuwig als rode ❌
in de PWA staan, omdat de match-op-reservering dan nooit iets vindt. Joris wilde
dit eerst handmatig houden, maar koos er op 7 aug 2026 alsnog voor toen de
wekelijkse herhaling erbij kwam — drie boekingen per week zouden anders
opstapelen. Termijn: de dag ná de speeldatum, zodat de ❌ zichtbaar blijft in het
venster waarin je nog handmatig een baan kunt zoeken.

**How to apply:** de datumlogica staat in `wachtrij_regels.py`, bewust vrij van
selenium-imports omdat `lees_reserveringen.py` zelf lokaal niet importeerbaar is.
Tests draaien met `python -m unittest discover -s tests -t .` vanaf de repo-root.
Zie [[project-knltb-locatie]] en [[project-wekelijkse-herhaling]].

---
name: project-wekelijkse-herhaling
description: "Elke dinsdag 20:00 draaien er automatisch drie boekingen — tennis onder Chris, padel onder Joris en Toine, met 12 vaste spelers."
metadata: 
  node_type: memory
  type: project
  originSessionId: f27712e9-ead3-4730-84a4-8a70e9f54141
  modified: 2026-08-07T10:55:26.191Z
---

Sinds 7 aug 2026 draait er een vaste wekelijkse reservering: elke **dinsdag
20:00** één tennisbaan onder Chris van Waardenburg en twee padelbanen onder
Joris van den Broek en Toine Aanraad, met 12 vaste spelers (vier per baan,
boeker op positie 0).

Geconfigureerd in `herhalingen.json`; `genereer_herhalingen.yml` maakt elke
maandag 06:00 NL wachtrij-items aan voor 4 weken vooruit, waarna de bestaande
wachtrij-flow het overneemt. Boekmoment is dus elke **zondag 07:00**
(speeldatum − 2).

**Why:** Joris koos bewust voor materialiseren als wachtrij-items in plaats van
een directe cron, zodat de items zichtbaar zijn in de PWA en een week overslaan
kan met de 🗑️-knop. Een `gegenereerd_tot`-watermark per regel zorgt dat een
verwijderd item niet de week erop terugkomt.

**How to apply:** week overslaan = 🗑️ in de PWA. Langer stoppen = `actief: false`
op de regel. Spelers wijzigen = `spelers` aanpassen; geldt pas vanaf de
eerstvolgende generatie, al ingeplande items houden de oude namen. Raak
`gegenereerd_tot` niet met de hand aan tenzij je bewust opnieuw wilt genereren.

**Bekend risico:** als ETV's "1 actieve reservering per lid" klopt
(`knltb-autoboek.md` 13.9, niet gevalideerd), legt dit beslag op de enige
reserveringsplek van alle 12 spelers van zondagochtend tot dinsdagavond. Bewust
geaccepteerd. Zie [[project-wachtrij-cleanup]] en [[project-knltb-locatie]].

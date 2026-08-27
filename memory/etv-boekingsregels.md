---
name: etv-boekingsregels
description: "ETV-clubregels die het boeken begrenzen - 1 actieve boeking per dag per lid, reserveren vanaf 07:00 twee dagen vooruit"
metadata: 
  node_type: memory
  type: project
  originSessionId: 50c05260-47d6-4529-b460-c1b81aa25aa7
  modified: 2026-08-26T17:20:33.034Z
---

Twee ETV-regels die niet uit de code blijken maar het gedrag bepalen:

- **Eén actieve boeking per dag per lid.** ETV weigert een tweede baan op
  dezelfde speeldatum met "X kan 1 actieve boekingen per dag hebben". Dat komt
  pas terug op de bevestig-POST, dus een dry-run kan het niet detecteren: die
  stopt juist vóór die klik. Let op dat een lid ook door iemand ánders aan een
  boeking kan zijn toegevoegd.
- **Reserveren mag vanaf 07:00 op speeldatum min 2 kalenderdagen.** De vaste
  herhalingen spelen op dinsdag, dus alle automatische runs vallen op zondag.

Tennisbaan 04 is de slechtste, vandaar hoogste baan eerst bij tennis.
Padel is schaars rond 20:00, tennis vrijwel nooit.

Padelbanen zijn NIET meer gelijkwaardig sinds 26-08-2026: Joris heeft een
voorkeur voor Padel 5 en 6 (vastgelegd in `PADEL_VOORKEUR_PER_ACCOUNT` in
boek_regels.py — dit weerspreekt de eerdere aanname "onderling gelijkwaardig"
uit 09-08-2026). Joris' account probeert eerst 6, dan 5; Toine's account
eerst 5, dan 6
(bewust tegengesteld, om te voorkomen dat ze naar dezelfde baan grijpen).
Dit is een vaste per-account override, geen automatische spreiding — Joris
en Toine boeken toch al op verschillende tijden (19:00 resp. 20:00), dus
botsingsgevaar speelt niet. Accounts zonder override (bv.
chris_van_waardenburg, die alleen tennis boekt) vallen terug op de
basisvolgorde `PADEL_BANEN` (4, 6, 5, 3, 2, 1) met de oude offset-rotatie.

De wachtrij wordt niet door GitHub's eigen cron getriggerd, maar door een
externe cron-job.org ping op verwerk_wachtrij.yml om 06:50 NL, die vervolgens
boek.yml aanroept voor items waarvan speeldatum-2 dagen == vandaag.

Zie ook [[verifieer-planning-claims]].

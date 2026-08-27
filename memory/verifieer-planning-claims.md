---
name: verifieer-planning-claims
description: "Joris corrigeert uitspraken over data en planning die niet geverifieerd zijn; controleer cron, wachtrij en weekdagen voordat je ze noemt"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 50c05260-47d6-4529-b460-c1b81aa25aa7
  modified: 2026-08-09T18:28:38.798Z
---

Noem geen weekdag, speeldatum of "wanneer draait de volgende run" zonder het
eerst uit te rekenen of op te zoeken. In de sessie van 09-08-2026 corrigeerde
Joris me twee keer: ik noemde 11-08 een maandag (het is dinsdag) en beloofde
"morgenochtend draait er een run" terwijl de wachtrij pas de zondag daarna aan
de beurt was.

**Why:** hij leest dit soort uitspraken als toezeggingen en plant erop. Een
verkeerde datum of een niet-bestaande run kost hem een speelavond, en het
ondermijnt het vertrouwen in de rest van de analyse — ook als die wél klopt.

**How to apply:** reken weekdagen uit met Python in plaats van uit het hoofd.
Voor "wanneer draait de volgende run": `verwerk_wachtrij.yml` triggert alleen
als `speeldatum - 2 dagen == vandaag`, dus lees de wachtrij en bereken het.
Zie ook [[etv-boekingsregels]].

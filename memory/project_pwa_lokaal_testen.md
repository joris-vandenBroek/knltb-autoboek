---
name: project-pwa-lokaal-testen
description: Valkuilen bij het lokaal testen van de knltb-autoboek PWA — preview-server ziet de L-schijf niet en api.github.com is geblokkeerd.
metadata: 
  node_type: memory
  type: project
  originSessionId: f27712e9-ead3-4730-84a4-8a70e9f54141
  modified: 2026-08-07T11:48:20.449Z
---

Twee omgevingsbeperkingen die het lokaal testen van `docs/index.html` in de weg
zitten (vastgesteld 7 aug 2026):

**1. De preview-server leest `launch.json` uit de startmap van de sessie**, niet
uit de repo. Start een sessie in het oude OneDrive-pad, dan pakt hij
`...\OneDrive - Pinkroccade\Documents 1\knltb-autoboek\.claude\launch.json` —
een vestigiaal bestand dat naar een verwijderde worktree wees. Bovendien ziet
dat serverproces de **L-schijf niet**: mapped drives zijn per logon-sessie, en
het UNC-pad werkte evenmin.

**Werkwijze die wél werkt:** kopieer `docs/` naar de scratchpad op C:, wijs de
`launch.json` in de *startmap* daarheen, en kopieer na elke edit opnieuw. Laat
de `launch.json` ín de repo (relatief `"docs"`) ongemoeid — die klopt voor een
sessie die wel op L: start.

**2. `api.github.com` is geblokkeerd in de ingebouwde browser**;
`raw.githubusercontent.com` niet. Alles wat via de GitHub-API laadt (wachtrij van
andere gebruikers, verwijderen, workflow-dispatch) faalt daar met
`TypeError: Failed to fetch`.

**Werkwijze:** stub `window.fetch` met realistische data en inspecteer de DOM.
Voor een dispatch: vang de POST naar `/actions/workflows/` af en controleer de
payload in plaats van hem echt te versturen. Het echte klikwerk moet een mens in
de geïnstalleerde PWA doen.

Zie [[project-knltb-locatie]].

---
name: project-sw-cachestrategie
description: Bewuste keuze om data-caching uit te zetten in sw.js (behalve leden.json en static assets)
metadata: 
  node_type: memory
  type: project
  originSessionId: 4581b325-9bff-46a4-8861-7a39cd945834
---

Reserveringen en wachtrij worden NOOIT gecached in de service worker — alleen netwerk.

**Why:** Gecachte reserveringen leidden tot bugs: annuleringen bleven zichtbaar, updates kwamen niet door, en medegebruikers zagen elkaars verouderde data. Offline werken is toch nutteloos (boeken/annuleren vereist netwerk).

**How to apply:** Als er ooit een reden is om data te cachen in sw.js, eerst expliciet bevestigen met de gebruiker. Huidige strategie: static assets (cache-first), index.html (network-first), leden.json (cache-first), alles anders altijd netwerk.

Zie ook [[project-beheer-matrix]] voor de parallel matrix-aanpak in beheer_reserveringen.yml.

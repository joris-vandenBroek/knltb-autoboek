---
name: feedback-altijd-docs-bijwerken
description: Staande opdracht — werk README.md en knltb-autoboek.md ALTIJD bij wanneer er relevante informatie in de code/flow wijzigt. Niet wachten op vraag.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 278ae86e-16be-4c33-8760-94a552782c1c
---

# Staande opdracht: docs altijd meebijwerken

Joris heeft expliciet gevraagd: **altijd** `README.md` en `knltb-autoboek.md` bijwerken zodra er relevante info in de codebase verandert. Niet wachten tot 'ie het vraagt.

**Wat telt als "relevante info":**
- Nieuwe of gewijzigde features (bv. retry-logica, wachtrij, agenda-koppeling)
- Wijzigingen in de boek-flow / timing / volgorde van stappen
- Nieuwe workflows of workflow-inputs
- Nieuwe of gewijzigde secrets / configuratie-stappen
- Wijzigingen in de PWA-interactie (kaarten, knoppen, gedrag)
- Wijzigingen in de annulering / data-flow
- Belangrijke bugfixes die het gedrag merkbaar wijzigen
- Toekomstige features / roadmap-items

**Wat NIET hoeft:**
- Pure refactors zonder gedragswijziging
- Logging-tweaks / extra diagnose
- Interne bookkeeping (variabel-naam, helper-functie)
- Triviale typo-fixes

**Praktisch:**
- Na elke significante commit: check of README/MD nog klopt
- Bij twijfel: bijwerken
- Beide files synchroon houden (README is overzicht, knltb-autoboek.md is dieper technisch)
- Eén commit per docs-update is prima (mag samen met de code-change of erna)

**Bestanden:**
- `README.md` — overzicht, install-instructies, troubleshooting
- `knltb-autoboek.md` — technische diepgang per onderdeel

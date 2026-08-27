---
name: project-chris-van-waardenburg
description: Chris van Waardenburg is toegevoegd als 3e boekende gebruiker (7 aug 2026); alleen het GEBRUIKERS_CONFIG-secret moest Joris zelf nog zetten.
metadata: 
  node_type: memory
  type: project
  originSessionId: f27712e9-ead3-4730-84a4-8a70e9f54141
  modified: 2026-08-07T11:39:43.342Z
---

Chris van Waardenburg (id `chris_van_waardenburg`, bondsnummer 18342515) is op
7 aug 2026 toegevoegd als derde boekende gebruiker in knltb-autoboek, naast
Joris van den Broek en Toine Aanraad. Let op de spelling: **Waardenburg** met
dubbel a.

Volledig afgerond: repo-kant in commit `7bd566c`, Joris zette zelf de entry
`chris_van_waardenburg` in het secret `GEBRUIKERS_CONFIG`, en een dry-run van
`boek.yml` bevestigde de ETV-login (run 31168116912, `URL na login: /mijn`).
Claude voert nooit credentials in — het secret zet Joris altijd zelf.

Twee keuzes die Joris toen maakte en die niet uit de code blijken:

- **Geen `calendar_id`** voor Chris — bewust geen Google Agenda-events, net als
  bij Toine.
- **Chris staat als `"gedeeld": true` in `gebruikers.json`** (sinds 7 aug 2026).
  Daardoor mogen Joris én Toine zijn boekingen in de PWA verwijderen; elkaars
  boekingen mogen ze niet weghalen. Die rechten zijn adviserend, geen
  beveiliging — iedereen deelt hetzelfde token.
- **Chris boekt niet zelf en krijgt de PWA niet.** Zijn account bestaat alleen
  zodat Joris of Toine "Chris van Waardenburg" in de gebruiker-selector kunnen
  kiezen en onder zijn ETV-account boeken. Alleen Joris en Toine hebben een PAT
  nodig — die hangt aan het apparaat dat dispatcht, niet aan de ETV-gebruiker.
- **Medegebruikers delen Joris' GitHub-PAT.** Alleen `joris-vandenBroek` is
  collaborator op de (publieke) repo; niemand krijgt een eigen GitHub-account.
  Dus geen collaborator-invite nodig bij een nieuwe gebruiker.

Procedure voor een volgende gebruiker staat in README.md → "Multi-user setup"
in [[project-knltb-locatie]].

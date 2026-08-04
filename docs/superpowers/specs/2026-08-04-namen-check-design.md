# Namen-check bij 2e reservering op dezelfde dag

**Datum:** 2026-08-04
**Status:** Approved

## Probleem

ETV Volley staat vermoedelijk maar 1 actieve reservering per lid toe (zie
`knltb-autoboek.md` sectie 13.9). Als een speler die al in een reservering
of wachtrij-item voor dag X zit, ook wordt toegevoegd aan een nieuwe
reservering voor diezelfde dag X, faalt de daadwerkelijke boeking bij ETV
(de dag-selectie wordt geweigerd — zie 13.8/13.9). Die mislukking gebeurt nu
pas op de reserveringsdatum zelf, tijdens de Selenium-flow, en verspilt een
GitHub Actions-run.

## Doel

Vóór het aanmaken van een reservering (direct of via wachtrij) controleren
of er al een reservering of ingeplande (wachtrij-)reservering bestaat voor
dezelfde speeldatum, en zo ja, of de spelerslijsten overlappen. Bij overlap:
foutmelding met de dubbele naam/namen, en de reservering NIET aanmaken.

## Scope

- **Cross-user:** de check kijkt over alle gebruikers heen (Joris + Toine +
  toekomstige gebruikers uit `gebruikers.json`), niet alleen de gebruiker
  die nu boekt. ETV's beperking geldt per lid, ongeacht wie de boeking
  aanmaakt.
- **Locatie:** client-side in de PWA (`docs/index.html`), in `boekBaan()`,
  vóór de `workflow_dispatch`-aanroep. Dit voorkomt een onnodige GitHub
  Actions-run en geeft de gebruiker direct feedback.
- **Databronnen:** `reserveringen_<gebruiker>.json` (actieve reserveringen,
  raw fetch) en `wachtrij/<gebruiker>/*.json` (ingeplande reserveringen,
  GitHub Contents API) — voor elke gebruiker uit `laadGebruikers()`.

## Ontwerp

### Trigger

In `boekBaan()`, direct na `btn.disabled = true` + spinner-weergave, vóór de
`workflow_dispatch`-POST naar `boek.yml`.

### Nieuwe helper: `_vindDubbeleSpelers(datum, nieuweSpelers)`

1. Haal `gebruikers` op via `laadGebruikers()` (gecached).
2. Voor elke gebruiker, parallel (`Promise.all`):
   - **Actieve reserveringen:** fetch `reserveringen_<id>.json`. Voor elk
     item met `datum === de opgegeven datum`: voeg `item.spelers` (indien
     aanwezig) toe aan een verzamel-Set van bestaande namen.
   - **Wachtrij:** fetch `wachtrij/<id>` via de Contents API (zelfde
     `ghHeaders`-patroon als de bestaande "Andere gebruikers"-sectie), haal
     de JSON-inhoud van elk bestand op. Voor elk item met
     `datum === de opgegeven datum` **dat niet "gefaald" is** (zelfde
     gefaald-berekening als elders in de PWA: boekdatum = speeldatum − 2
     dagen; gefaald als boekdatum in het verleden ligt, of vandaag is én de
     tijd al voorbij 07:00 is): voeg `item.spelers` toe aan de Set.
3. Retourneer de sub-lijst van `nieuweSpelers` die ook in de Set van
   bestaande namen voorkomt (dubbele namen).
4. **Fail-open:** elke fetch-fout (netwerk, 404, parse-fout) voor een
   individuele gebruiker/bron wordt stilzwijgend overgeslagen (`catch` →
   niets toevoegen aan de Set). Als de hele functie onverwacht faalt, geeft
   ze een lege lijst terug (`console.warn`, geen blokkade). De check mag
   nooit een legitieme boeking tegenhouden puur omdat de check zelf
   netwerkproblemen had.

### Nieuwe spelers-lijst voor de check

`[eigenNaam, speler2, speler3, speler4].filter(Boolean)`, waarbij
`eigenNaam` de `naam` is van de huidige gebruiker uit `laadGebruikers()`
(lookup op `getGebruiker()`). Als de lookup faalt, wordt `eigenNaam`
weggelaten (check gaat door met de 3 bekende namen).

### Bij dubbele namen gevonden

- Toon `toonToast('error', ...)` met tekst:
  `⚠️ <namen, komma-gescheiden> staat/staan al (in)gepland op <datum NL>. Een speler kan niet in 2 reserveringen op dezelfde dag zitten.`
  (enkelvoud "staat" bij 1 naam, meervoud "staan" bij meerdere.)
- Reset de knop (`btn.disabled = false`, tekst terug naar normaal/dry-run).
- `return` — geen `workflow_dispatch`-aanroep, dus geen wachtrij-item en
  geen directe boeking.

### Bij geen dubbele namen

Ga door met de bestaande flow (ongewijzigd).

## Niet in scope

- Geen wijziging aan `boek_baan.py` of de workflows — de check gebeurt
  uitsluitend client-side vóór het aanmaken.
- Geen check op duplicaten binnen dezelfde nieuwe reservering (dat bestaat
  al in `valideer()`).
- Geen retroactieve check van al bestaande reserveringen/wachtrij-items
  onderling.

## Testplan

- Reservering aanmaken voor een dag met een bestaande actieve reservering
  of wachtrij-item mét overlappende speler → foutmelding, geen
  workflow-trigger (verifiëren via GitHub Actions-run-lijst).
- Zelfde dag, geen overlappende spelers → normale flow, workflow wordt wél
  getriggerd.
- Overlap met een "gefaald" wachtrij-item → mag NIET blokkeren.
- Gesimuleerde fetch-fout (bv. offline of ongeldige PAT) → boeking gaat
  gewoon door (fail-open), geen crash of hang.

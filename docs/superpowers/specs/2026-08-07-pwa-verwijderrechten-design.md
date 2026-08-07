# Boekingen van andere gebruikers zien en verwijderen

**Datum:** 2026-08-07
**Status:** Approved

## Probleem

De PWA toont de boekingen van andere gebruikers alleen aan Joris:
`laadAndereGebruikers()` (`docs/index.html:1614`) begint met
`if (getGebruiker() !== BEHEER_EIGENAAR) { sectie.style.display = 'none'; return; }`.
Toine ziet dus niets van Joris of Chris.

Die lijsten zijn bovendien read-only: `_renderReservList(items, false)` laat de
🗑️ weg. Chris boekt niet zelf — Joris en Toine boeken namens hem — maar niemand
kan een boeking van Chris opruimen zonder in de repo te duiken.

## Doel

1. Iedereen ziet de boekingen van alle gebruikers.
2. Boekingen van een **gedeeld account** (Chris) mag iedereen verwijderen.
3. Boekingen van een **persoonlijk account** mag alleen de eigenaar verwijderen.

## Scope

**Wel:** `docs/index.html`, `docs/sw.js` (cache-versie), `gebruikers.json`
(één veld).

**Niet:** `boek_baan.py`, `lees_reserveringen.py`, workflows, de beheer-UI
(🛠️) — die houdt zijn eigen `BEHEER_EIGENAAR`-gate voor het toevoegen en
verwijderen van *gebruikers*, wat iets anders is dan boekingen.

## Uitdrukkelijk géén beveiliging

Toine gebruikt Joris' GitHub-PAT (zie `README.md` → Multi-user setup). Met dat
token kan hij via de GitHub-API elk bestand in de repo verwijderen, ongeacht wat
de PWA toont. Deze rechten zijn **client-side en dus adviserend**: een drempel
tegen per ongeluk klikken, geen beveiligingsgrens.

Echte afdwinging zou aparte GitHub-accounts met eigen tokens vereisen. Dat is op
2026-08-07 bewust afgewezen ten gunste van één gedeeld token. Wie dat later
alsnog wil, moet deze rechten opnieuw ontwerpen — niet uitbreiden.

## Ontwerp

### 1. Gedeelde accounts in `gebruikers.json`

```json
{ "id": "chris_van_waardenburg", "naam": "Chris van Waardenburg", "gedeeld": true }
```

Ontbreekt `gedeeld`, dan is het een persoonlijk account. Het veld is
niet-gevoelig en hoort thuis naast `id` en `naam`.

### 2. Rechtenregel

Eén helper, gebruikt door beide renderpaden:

```javascript
function magVerwijderen(eigenaarId) {
  return eigenaarId === getGebruiker() || _isGedeeld(eigenaarId);
}
```

`_isGedeeld(id)` leest de gecachete lijst uit `laadGebruikers()`
(`_gebruikersCache`) en is dus **synchroon**.

**De volgorde van die twee condities is load-bearing.** `_gebruikersCache` kan
`null` zijn wanneer `_renderReservList` vanuit `laadReserveringen()` wordt
aangeroepen — die wacht niet op `laadGebruikers()`. De eigen-eigenaarscheck staat
daarom vooraan: die heeft de cache niet nodig, dus de 🗑️ op je eigen lijst
verschijnt hoe dan ook. De `_isGedeeld`-tak wordt alleen bereikt vanuit
`laadAndereGebruikers()`, dat wél `await laadGebruikers()` doet vóór het
renderen. Draai je de condities om, dan verdwijnt de knop soms van je eigen
lijst — een regressie die alleen bij een koude cache optreedt en dus makkelijk
door tests glipt.

De regel is **symmetrisch**: Joris mag Toine's boekingen net zo min verwijderen
als andersom. Bewust gekozen op 2026-08-07 boven een beheerdersrol voor Joris.

### 3. Zichtbaarheid

In `laadAndereGebruikers()`:

- De `BEHEER_EIGENAAR`-gate vervalt.
- Het filter `g.id !== BEHEER_EIGENAAR` wordt `g.id !== getGebruiker()` — je
  eigen boekingen staan al in de hoofdkaarten, die hoeven er niet nog een keer
  onder.

### 4. Twee soorten verwijderen

**Wachtrij-item (🕒 gepland).** `verwijderWachtrij(btn, path, sha)` werkt al op
een pad en is dus gebruiker-agnostisch. Alleen de knop ontbreekt in de
andere-gebruikers-render; die wordt voorwaardelijk op `magVerwijderen(g.id)`.

**Reservering (📅 actief).** `annuleerReservering` roept nu
`_dispatchBeheer(pat, getGebruiker(), id)` aan — de *geselecteerde* gebruiker,
niet de eigenaar van de reservering. Zou je de knop zonder meer aanzetten, dan
logt de workflow in op het verkeerde ETV-account en probeert daar een cancel-ID
te annuleren dat niet bestaat.

Daarom:

- `_renderReservList(items, toonDel, eigenaarId)` geeft `eigenaarId` mee aan de
  onclick.
- `annuleerReservering(btn, id, datum, tijd, eigenaarId)` stuurt die door naar
  `_dispatchBeheer`. Zonder argument valt hij terug op `getGebruiker()`, zodat de
  bestaande aanroep voor je eigen lijst ongewijzigd blijft werken.

### 5. Service worker

`docs/sw.js`: `CACHE` van `'padel-v59'` naar `'padel-v60'`. Verplicht zodra
`docs/index.html` inhoudelijk verandert (`knltb-autoboek.md` sectie 7), anders
serveert de SW de oude pagina.

## Foutafhandeling

Ongewijzigd. Bestaande paden blijven gelden: geen PAT → toast "Stel eerst je
GitHub Token in"; mislukte dispatch → toast met HTTP-status; netwerkfout →
toast. Het annuleren van andermans reservering gebruikt exact dezelfde
`_dispatchBeheer`-flow, dus ook dezelfde foutmeldingen.

Een gebruiker die niet in `gebruikers.json` staat (bijvoorbeeld na een
verwijdering terwijl de PWA nog open staat) levert `_isGedeeld() === false` op —
dus geen knop. Fail-closed: bij twijfel geen verwijderrecht.

## Testen

Handmatig in de browser via een lokale server (`python -m http.server` op
`docs/`), met de gebruiker-selector als schakelaar:

| Als | Bij eigen lijst | Bij Chris | Bij de andere persoon |
|-----|-----------------|-----------|-----------------------|
| Joris | 🗑️ zichtbaar | 🗑️ zichtbaar | géén 🗑️ |
| Toine | 🗑️ zichtbaar | 🗑️ zichtbaar | géén 🗑️ |

Plus: controleer in de netwerk-tab dat het annuleren van een reservering van
Chris een `workflow_dispatch` stuurt met `gebruiker=chris_van_waardenburg` en
niet met de ingelogde gebruiker. Dat is de enige regressie die stil zou kunnen
falen.

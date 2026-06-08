# knltb-autoboek â€” Volledige documentatie

**GitHub-repository:** `joris-vandenBroek/knltb-autoboek`  
**Doel:** Automatisch een padelbaan reserveren bij ETV Volley via de KNLTB-ledenportal, aangestuurd via een PWA op de telefoon, inclusief Google Agenda-integratie en wachtrij voor toekomstige reserveringen.

---

## Inhoudsopgave

1. [Hoe werkt het in grote lijnen](#1-hoe-werkt-het-in-grote-lijnen)
2. [Repository-structuur](#2-repository-structuur)
3. [Benodigde GitHub Secrets](#3-benodigde-github-secrets)
4. [Externe cron-trigger via cron-job.org](#4-externe-cron-trigger-via-cron-joborg)
5. [PWA-frontend â€” docs/index.html](#5-pwa-frontend--docsindexhtml)
6. [Service Worker â€” docs/sw.js](#6-service-worker--docsswjs)
7. [Workflows](#7-workflows)
8. [boek_baan.py â€” stap voor stap](#8-boek_baanpy--stap-voor-stap)
9. [lees_reserveringen.py â€” reserveringen + annuleren](#9-lees_reserveringenpy--reserveringen--annuleren)
10. [haal_leden_op.py â€” ledenlijst scrapen](#10-haal_leden_oppy--ledenlijst-scrapen)
11. [Technische valkuilen en beslissingen](#11-technische-valkuilen-en-beslissingen)
12. [Wijzigingen aanbrengen](#12-wijzigingen-aanbrengen)
13. [Toekomstige features â€” multi-user setup](#13-toekomstige-features--multi-user-setup)
14. [Operationele veiligheidsnetten](#14-operationele-veiligheidsnetten)

---

## 1. Hoe werkt het in grote lijnen

```
Gebruiker (telefoon)
        â”‚  tikt op "Baan reserveren" in de PWA
        â–¼
docs/index.html (GitHub Pages PWA)
        â”‚  POST naar GitHub Actions API (met PAT-token)
        â–¼
.github/workflows/boek.yml
        â”‚  Start Python-script met datum/tijd/spelers
        â–¼
boek_baan.py
        â”‚  IF speeldatum > dag+2:
        â”‚     â†’ schrijf wachtrij/<datum>_<tijd>.json + commit/push
        â”‚  ELSE:
        â”‚     â†’ login + spelers + (wacht tot 07:01 NL) + dag + baan + bevestig
        â–¼
Google Agenda  (via Service Account, optioneel)
        â–¼
Klaar â€” e-mail van ETV Volley + agenda-event

â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘ Voor wachtrij-items (dag+3 en verder):                   â•‘
â•‘                                                          â•‘
â•‘ cron-job.org (06:50 NL dagelijks)                        â•‘
â•‘     â”‚  POST naar GitHub Actions API                      â•‘
â•‘     â–¼                                                    â•‘
â•‘ verwerk_wachtrij.yml                                     â•‘
â•‘     â”‚  Voor elk wachtrij-bestand met                     â•‘
â•‘     â”‚  reserveringsdatum == vandaag:                         â•‘
â•‘     â”‚     â†’ triggert boek.yml met die inputs             â•‘
â•‘     â–¼                                                    â•‘
â•‘ boek.yml â†’ boek_baan.py â†’ dag-keuze vanaf 07:01 NL âœ“     â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
```

De **ledenlijst** (`leden.json`) wordt los bijgehouden via `haal_leden_op.yml` (wekelijks of handmatig). Gebruikt door de PWA voor de speler-dropdowns.

De **actieve reserveringen** (`reserveringen.json`) worden bijgehouden via `lees_reserveringen.py` + `beheer_reserveringen.yml`, getriggerd vanuit de PWA bij Verversen of Annuleren.

---

## 2. Repository-structuur

```
knltb-autoboek/
â”œâ”€â”€ boek_baan.py                 # Hoofdscript: Selenium-reservering + wachtrij
â”œâ”€â”€ lees_reserveringen.py        # Scrape + annuleer actieve reserveringen
â”œâ”€â”€ haal_leden_op.py             # Scrape de ledenlijst â†’ leden.json
â”œâ”€â”€ leden.json                   # Cache van alle ETV-leden (~970 namen)
â”œâ”€â”€ reserveringen.json           # Cache van actieve reserveringen
â”œâ”€â”€ wachtrij/                    # Reserveringen voor speeldatums > dag+2
â”‚   â”œâ”€â”€ .gitkeep
â”‚   â””â”€â”€ YYYY-MM-DD_HHMM.json     # Per ingeplande reservering
â”œâ”€â”€ docs/                        # PWA (GitHub Pages source)
â”‚   â”œâ”€â”€ index.html               # Single-page app
â”‚   â”œâ”€â”€ sw.js                    # Service Worker (cache versioning)
â”‚   â”œâ”€â”€ manifest.json            # PWA-manifest
â”‚   â”œâ”€â”€ logo.png + icon-192/512.png
â””â”€â”€ .github/workflows/
    â”œâ”€â”€ boek.yml                 # Voer een reservering uit
    â”œâ”€â”€ verwerk_wachtrij.yml     # Verwerk wachtrij (door cron-job.org getriggerd)
    â”œâ”€â”€ beheer_reserveringen.yml # Scrape of annuleer reservering (vanuit PWA)
    â””â”€â”€ haal_leden_op.yml        # Ledenlijst-refresh (maandag 07:00)
```

GitHub Pages is ingesteld op de `docs/`-map van de `main`-branch. De PWA is bereikbaar via `https://joris-vandenbroek.github.io/knltb-autoboek/`.

---

## 3. Benodigde GitHub Secrets

In te stellen via **GitHub â†’ Repository â†’ Settings â†’ Secrets and variables â†’ Actions**:

| Secret | Inhoud |
|--------|--------|
| `ETVVOLLEY_BONDSNUMMER` | Bondsnummer / gebruikersnaam voor etv-volley.nl |
| `ETVVOLLEY_WACHTWOORD` | Wachtwoord voor etv-volley.nl |
| `GOOGLE_CALENDAR_CREDENTIALS` | Volledige JSON-inhoud van het Service Account-sleutelbestand |
| `GOOGLE_CALENDAR_ID` | Agenda-ID (bijv. `primary` of e-mailadres) |
| `HEALTHCHECK_PING_URL` *(optioneel)* | Healthchecks.io check URL voor dead-man's-switch (zie sectie 14) |

Het **GitHub Personal Access Token (PAT)** wordt *niet* als Secret opgeslagen, maar:
- **In de PWA** in `localStorage` (sleutel `knltb_pat`) voor PWA-triggers (workflow_dispatch)
- **In cron-job.org** in een header voor de dagelijkse wachtrij-trigger

Beide PATs hebben minimaal `workflow` scope nodig (classic) of `Actions: Read and write` op deze repo (fine-grained).

---

## 4. Externe cron-trigger via cron-job.org

**Waarom extern?** GitHub Actions' eigen `schedule:`-triggers zijn best-effort en kunnen volledig overgeslagen worden, vooral bij nieuwe workflows of tijdens hoge load. Dit gebeurde inderdaad op de eerste productie-nacht: de cron `'55 4 * * *'` in `verwerk_wachtrij.yml` vuurde simpelweg niet, ook al was de workflow `active`. cron-job.org is een externe service die wÃ©l deterministisch op tijd vuurt.

### Setup

1. **Classic PAT aanmaken** op [github.com/settings/tokens/new](https://github.com/settings/tokens/new):
   - Scope: alleen `workflow` (geeft automatisch `repo`-rechten)
   - Expiration: bv. 1 jaar
2. **Account** op [cron-job.org](https://cron-job.org) â†’ Create cronjob:
   - **URL:** `https://api.github.com/repos/joris-vandenBroek/knltb-autoboek/actions/workflows/verwerk_wachtrij.yml/dispatches`
   - **Schedule:** Every day at **06:50**, timezone **Europe/Amsterdam**
   - **Request method:** POST
   - **Request body:** `{"ref":"main"}`
   - **Headers:**
     | Name | Value |
     |---|---|
     | `Authorization` | `Bearer ghp_...` |
     | `Accept` | `application/vnd.github+json` |
     | `X-GitHub-Api-Version` | `2022-11-28` |
     | `Content-Type` | `application/json` |
3. **Test run** â†’ moet 204 No Content geven

### Trade-offs

- âœ… Betrouwbaar (vuurt op tijd)
- âœ… Heeft notificaties bij failure
- âš ï¸ Externe service heeft je PAT
- âš ï¸ Cron-job.org gratis tier heeft een limiet (~1 trigger/min, ruim voldoende voor dagelijks)

---

## 5. PWA-frontend â€” docs/index.html

EÃ©n HTML-bestand zonder frameworks. Werkt als installeerbare PWA op iPhone en Android. Sectie-volgorde:

1. **Header** met ETV Volley-logo + âš™ï¸-knop voor PAT
2. **Wanneer** â€” datumkiezer + tijdkeuze (08:00â€“21:30, stappen van 30 min, standaard 15:00)
3. **Medespelers** â€” 3 dropdowns met zoekfilter (PrimeFaces-stijl)
4. **ðŸ“… Mijn reserveringen** â€” actieve reserveringen + ðŸ—‘ï¸ annuleren per item
5. **ðŸ•’ Ingeplande reserveringen** â€” wachtrij + ðŸ—‘ï¸ verwijderen per item
6. **ðŸŽ¾ Baan reserveren** â€” vast onderaan, triggert workflow

### Mobile sizing

Basis font-size `22px` (op viewport < 380px: `20px`). Velden minimaal 58px hoog, knoppen 76px. Doel: comfortabel tappen op midrange telefoons (S10+, iPhone 12, etc.).

### Date-picker click-fix

De native `<input type="date">` ligt als transparante overlay op de visuele knop. CSS-regel `pointer-events: none` op `.date-native` zorgt dat het hele veld klikbaar is (niet alleen het smalle kalender-icoon-gebied dat sommige browsers default geven). De JS-handler op `.date-picker-btn` roept `showPicker()` aan.

### Mijn reserveringen (PWA-card)

```javascript
const RESERV_URL = `https://raw.githubusercontent.com/${REPO}/main/reserveringen.json`;
```

- **Laden op page open:** fetch `reserveringen.json` van GitHub raw, render lijst.
- **ðŸ”„ Verversen:** workflow_dispatch op `beheer_reserveringen.yml` met `cancel_id=""` â†’ script logt in, scrape, commit/push update naar `reserveringen.json`. PWA pollt 4Ã— tussen 90s en 180s om nieuwe state te tonen.
- **ðŸ—‘ï¸ Annuleer-knop per item:** confirm-dialoog â†’ workflow_dispatch met `cancel_id="YYYY-MM-DD_HHMM_baan-slug"` â†’ script annuleert op ETV-site + verwijdert agenda-event + ververst lijst.

### Ingeplande reserveringen (wachtrij, PWA-card)

```javascript
const WACHTRIJ_API = `https://api.github.com/repos/${REPO}/contents/wachtrij`;
```

- Leest direct via Contents API (geen tussenstap nodig â€” alleen files in `wachtrij/`).
- Toont per item: speeldatum, tijd, spelers, reserveringsdatum.
- ðŸ”„ Verversen herlaadt de Contents API.
- ðŸ—‘ï¸ verwijdert het JSON-bestand via Contents API DELETE (geen workflow nodig).

### PAT-overlay

Verschijnt automatisch als `localStorage.knltb_pat` leeg is. PAT opgeslagen lokaal â€” niet naar server gestuurd.

### Validatie

Velden krijgen rode rand bij leeg laten bij druk op "Baan reserveren". Hidden `<input>` per speler-slot wordt alleen ingevuld als dropdown-keuze gemaakt is.

### XSS-bescherming

Alle gerenderde user-data gaat door `escapeHtml()` (in beide wachtrij- en reserveringen-render). Voorkomt HTML-injection als een spelernaam ooit speciale tekens bevat.

---

## 6. Service Worker â€” docs/sw.js

```javascript
const CACHE = 'padel-v16';
```

Elke keer dat `index.html` of `sw.js` inhoudelijk verandert moet dit versienummer omhoog (huidige stand: v16). De SW verwijdert dan automatisch de oude cache bij activate.

### Cachestrategie per bestandstype

| Bestanden | Strategie | Reden |
|-----------|-----------|-------|
| `index.html`, `manifest.json`, `/` | **Network-first**, fallback cache | Updates direct zichtbaar |
| `sw.js`, `logo.png`, `icon-*.png` | **Cache-first** | Veranderen zelden |
| `leden.json`, `api.github.com` | **Altijd netwerk**, fallback cache | Altijd vers |
| Overige | Cache-first | Afbeeldingen/icons |

`raw.githubusercontent.com/.../reserveringen.json` wordt automatisch cache-busted via `?t=` timestamp query.

**Belangrijk:** na een wijziging aan `index.html` moet `CACHE` versie in `sw.js` omhoog, anders zien gebruikers de oude versie. Sommige browsers updaten de SW pas na hard-refresh of app dood-swipen + opnieuw openen.

---

## 7. Workflows

### 7.1 boek.yml

**Trigger:** alleen `workflow_dispatch`.

**Inputs:** `datum` (YYYY-MM-DD), `tijd` (HH:MM), `speler2`, `speler3`, `speler4`.

```yaml
jobs:
  boek:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: write          # Voor wachtrij-commits
    env:
      TZ: Europe/Amsterdam     # boek_baan.py's datetime.now() in NL-tijd
```

**Stappen:** checkout â†’ setup-python 3.11 â†’ `apt-get install xvfb` + pip install (undetected-chromedriver, selenium, google-api-python-client, google-auth) â†’ `Xvfb :99` + `python boek_baan.py ...` â†’ bij fout: upload `*.png` als artifact (3 dagen retentie).

### 7.2 verwerk_wachtrij.yml

**Trigger:** `workflow_dispatch` (door cron-job.org) of `schedule` (GitHub-side fallback, kan overgeslagen worden).

```yaml
on:
  schedule:
    - cron: '55 4 * * *'    # 06:55 CEST zomertijd (best-effort)
    - cron: '55 5 * * *'    # 06:55 CET wintertijd (best-effort)
  workflow_dispatch:
```

**Skip-logica:** alleen voor `schedule`-events checken op tijd-venster (06:55-07:30 NL); workflow_dispatch (= cron-job.org) draait altijd direct.

**Wat het doet:**
1. Lees `wachtrij/*.json`
2. Per bestand: bereken `reserveringsdatum = speeldatum - 2 dagen`
3. Als `reserveringsdatum == today` (NL-tijd):
   - `gh workflow run boek.yml --field datum=... --field tijd=... --field speler2=... etc.`
   - Verwijder het wachtrij-bestand
4. Commit + push de verwijderingen (retry-loop met rebase)

### 7.3 beheer_reserveringen.yml

**Trigger:** alleen `workflow_dispatch`.

**Input:** `cancel_id` (optioneel â€” formaat `YYYY-MM-DD_HHMM_baan-slug`).

```yaml
permissions:
  contents: write
env:
  TZ: Europe/Amsterdam
```

Run: `python lees_reserveringen.py` (of met `--cancel ID`). Schrijft `reserveringen.json` en commit.

### 7.4 haal_leden_op.yml

**Trigger:** `workflow_dispatch` of `schedule: '0 5 * * 1'` (07:00 NL maandag, zomertijd).

**Permissions:** `contents: write` voor `leden.json` push (met retry-loop).

---

## 8. boek_baan.py â€” stap voor stap

### Constanten

```python
LOGIN_URL     = "https://www.etv-volley.nl/mijn"
RESERVEER_URL = "https://www.etv-volley.nl/mijn/Reservations"
SPELER1       = "Joris van den Broek"   # altijd speler 1
PADEL_BANEN   = ["Padel 1", ..., "Padel 6"]
```

### Wachtrij-pad

```python
reserveringsdatum = speeldatum - timedelta(days=2)

if nu.date() < reserveringsdatum.date():
    _zet_in_wachtrij(args.datum, args.tijd, args.speler2, args.speler3, args.speler4)
    sys.exit(0)
```

`_zet_in_wachtrij()`:
1. Schrijf `wachtrij/<datum>_<tijdslug>.json` met `datum`, `tijd`, `spelers` (4 namen), `ingediend` timestamp
2. `git add` + `git commit` + push met retry-loop (max 5 pogingen, `git pull --rebase` tussen elke poging)

### Direct-boek-pad

1. **Login** â€” Cloudflare-wait, cookie-banner, JS-property setter voor bondsnummer + wachtwoord (triggert React/Vue input/change events), submit
2. **Klik "Baan afhangen"** op de Reserveringen-pagina
3. **Voeg 3 spelers toe** â€” zie volgende sectie
4. **Wacht tot 07:01 NL** als nodig (zie [boekvenster-timing](#boekvenster-timing-op-0701-nl))
5. **Kies dag + dagdeel** â€” retry-loop met back-redirect recovery (max 3 pogingen)
6. **Kies tijdslot** â€” zoekt `.timeincourt` of `[data-hour]` cellen in de padel-rij via absolute Y-positie
7. **Bevestig** â€” intercepteert jQuery.ajax POST naar `/Ajax/Profile/SaveReservation`
8. **Verifieer** â€” bezoek `/mijn/Reservations` en `/me/Reservations`, check op datum + tijd in body
9. **Google Agenda-event** â€” Service Account API call, kleur groen, popup-herinnering 60 min

### Strikte spelers-matching

Een element wordt **alleen** geklikt als zijn genormaliseerde innerText EXACT gelijk is aan:
- Volledige naam (bv. "Chris van Waardenburg")
- OF voornaam + achternaam zonder tussenvoegsel (bv. "Chris Waardenburg")

**Achternaam-alleen wordt NOOIT geaccepteerd als match-tekst.** De achternaam wordt wel gebruikt als laatste zoekterm-fallback (bv. typen "Waardenburg" om de typeahead te triggeren), maar het te klikken element moet alsnog exact "Chris van Waardenburg" zijn.

**Selectors (in volgorde):**
1. `//*[@role='option']`
2. `//li[contains(., 'achternaam')]`
3. `//div[contains(@class, 'player|suggestion|result|item')]`

**GÃ©Ã©n brede `//*` fallback** â€” die matchte het "Recent mee gespeeld" paneel en koppelde een verkeerde click-handler. Zie [valkuilen](#114-recent-mee-gespeeld-race-condition).

**Post-klik verificatie:** na elke speler-click moet de doelnaam zichtbaar zijn op de pagina in een non-input element. Zo niet â†’ `return False`, hele reservering faalt. Beter falen dan een verkeerde speler reserveren.

### kies_dag retry-loop

3 pogingen met automatisch herstel:
- VÃ³Ã³r elke poging: detecteer huidige URL. Als op `ReservationsPlayers` (back-redirect van eerdere poging): klik Volgende om weer naar dag-pagina.
- Re-fetch daypart-element + Volgende-knop in elke poging (geen stale references).
- Klik daypart via ActionChains (isTrusted=true) â€” synthetische events worden door ETV's jQuery genegeerd.
- Na submit: 4 mogelijke outcomes:
  1. URL = `ReservationsCourt` â†’ success
  2. Body bevat `:00` of `:30` â†’ AJAX-wizard success
  3. URL = `ReservationsPlayers` â†’ server weigerde dagdeel â†’ retry
  4. Onbekend â†’ retry

### Boekvenster-timing op 07:01 NL

```python
# Vlak vÃ³Ã³r kies_dag:
doel = reserveringsdatum.replace(hour=7, minute=1, second=0)
if nu.date() == reserveringsdatum.date() and nu < doel:
    time.sleep(int((doel - nu).total_seconds()))

kies_dag(driver, ...)
kies_baan_en_tijd(driver, ...)
bevestig(driver)
```

Cron-job.org triggert om **06:50 NL**. Login + spelers (~3-4 min) loopt tijdens de wachttijd vÃ³Ã³r 07:00 â€” die stappen hebben geen slot-validatie. **Vanaf 07:01 NL** (1 min buffer voor klok-skew) doet het script kies_dag â†’ kies_baan_en_tijd â†’ bevestig in Ã©Ã©n doorloop. Bevestig valt rond 07:02-03.

**Waarom de wait vÃ³Ã³r kies_dag, niet vÃ³Ã³r bevestig?** Run #63 bewees dat ETV's server de daypart-selectie zelf weigert vÃ³Ã³r 07:00 â€” de Volgende-klik na het clicken van een daypart krijgt geen navigatie en het script faalt na 3 retries. De slot-opening om 07:00 geldt voor de **hele wizard vanaf dag-keuze**, niet alleen bevestig. Zie [valkuilen 11.9](#119-boekvenster-geldt-vanaf-dag-keuze-niet-alleen-bevestig).

### bevestig + BEZET-retry (race-conditie tussen kies en bevestig)

Vlak na 07:00 NL claimen meerdere clubleden tegelijk een padelbaan. Het venster tussen `kies_baan_en_tijd` (baan klikken â†’ Volgende) en `bevestig` (Bevestig-knop) is ~1-2 seconden, en in die seconden kan iemand anders nÃ©t sneller dezelfde baan vastleggen. De server reageert dan op onze `SaveReservation`-POST met een melding als "niet gevonden", "al gereserveerd", "reeds geboekt" of "niet meer beschikbaar".

**Detectie in `bevestig()`** â€” die functie retourneert sinds commit 1675acf een 3-state string:

| Return | Betekenis |
|---|---|
| `'OK'`    | Reservering geslaagd |
| `'BEZET'` | Server wees af met race-loss-patroon â†’ main() doet retry met andere baan |
| `'FOUT'`  | Andere fout â†’ script stopt (geen retry zinvol) |

**Retry-loop in main()** (max 6 pogingen, gelijk aan aantal padelbanen):

```python
for baan_poging in range(1, 7):
    baan, tijd = kies_baan_en_tijd(driver, args.tijd)
    if not baan: sys.exit(1)
    resultaat = bevestig(driver)
    if resultaat == 'OK':   break
    if resultaat == 'BEZET':
        driver.get("https://www.etv-volley.nl/me/ReservationsCourt")
        time.sleep(2)
        driver.refresh()   # garandeer verse DOM (geen browser-cache)
        time.sleep(2)
        continue
    sys.exit(1)  # FOUT
```

**Waarom geen uitsluit-lijst van banen?** ETV's baan-keuze pagina toont bezette tijdcellen simpelweg niet meer in de DOM na een verse load. `kies_baan_en_tijd` itereert al per voorkeur-tijd over alle Padel 1-6 (kiest de tijdcel Y-dichtstbij een Padel-label) en valt pas terug op alternatieve tijden als alle padelbanen voor de voorkeur-tijd weg zijn. De pagina-refresh + DOM-state IS dus zelf de filter â€” geen aparte `uitgesloten_banen`-administratie nodig.

**Gedrag bij race:**
```
Baan-poging 1/6 â†’ Padel 1 om 15:00 â†’ bevestig: BEZET
  âŸ³ /me/ReservationsCourt + driver.refresh()
Baan-poging 2/6 â†’ Padel 2 om 15:00 (Padel 1 weg uit DOM) â†’ bevestig: OK âœ…
```

### Diagnose-logging

Na elke wizard-stap dumpt het script welke spelers zichtbaar zijn op de huidige pagina:

```
ðŸ“Š SPELERS-CHECK [na voeg_spelers_toe (4 verwacht)] URL=.../ReservationsDay
   âœ“ Aanwezig (4/4): [...]
```

Bij "MIST 3 van 4" weten we direct waar in de wizard de server-side state verloren is gegaan.

---

## 9. lees_reserveringen.py â€” reserveringen + annuleren

### Werking

Zonder argumenten: scrape `/mijn/Reservations`, schrijf `reserveringen.json`, commit/push.

Met `--cancel <id>`: annuleer die reservering (klik Annuleren-knop in rij met matching datum+tijd), bevestig dialoog, dan opnieuw scrape. Plus: verwijder matching Google Agenda-event (zoekt 'Padel'-events in window -1u tot +2u rond het slot, matcht op start-datetime + 'Padel' in summary).

### ID-format

`YYYY-MM-DD_HHMM_baan-slug`, bijv. `2026-05-31_1500_padel-1`. Wordt deterministisch gebouwd in `maak_id()` zodat PWA en script dezelfde ID gebruiken.

### Scrape-heuristieken

Drie strategieÃ«n:
1. **Tabel-rijen** â€” alle `<tr>` met â‰¥2 `<td>` cellen
2. **Class-based divs** â€” `[class*="booking|reservation|reservering|reservering"]`
3. **Cancel-buttons** â€” `<button|a|[role=button]>` met tekst/class/title/aria-label bevattend `annuleer|cancel|verwijder|delete|prullenbak`

Per kandidaat: regex op `datum`, `tijd`, `baan` (Padel/Tennis N). Cancel-button wordt gekoppeld aan rij via parent-tekst-match.

Output:
```json
{
  "bijgewerkt": "2026-05-29T09:21:39",
  "reserveringen": [
    {
      "id": "2026-05-31_1500_padel-1",
      "datum": "2026-05-31",
      "tijd": "15:00",
      "baan": "Padel 1",
      "tekst": "...",
      "cancel": { "btnTekst": "Annuleren", ... }
    }
  ]
}
```

---

## 10. haal_leden_op.py â€” ledenlijst scrapen

1. Login via Selenium/UC (zelfde patroon)
2. Klik "Ledenlijst"-tab
3. Scrape namen uit eerste tabelkolom: `name.length > 3 && name.indexOf(' ') >= 0`
4. **Paginering** â€” klik paginanummer N+1, fallback `Â»` / "Volgende" / `â€º`
5. **Fallback per letter** â€” als <10 namen na alle pagina's: door alfabet en filter op Ã©Ã©n letter
6. Sorteer + schrijf `leden.json` + commit/push met retry-loop

Cron `'0 5 * * 1'` = maandag 07:00 NL (zomertijd; in winter wordt het 06:00 â€” niet kritiek voor ledenlijst-refresh).

---

## 11. Technische valkuilen en beslissingen

### 11.1 Cloudflare-omzeiling

`undetected-chromedriver` past de Chrome binary aan zodat Cloudflare-detectie (`navigator.webdriver`) faalt. **Geen `--headless`**: headless-modus laat signatures achter die Cloudflare herkent. Xvfb simuleert een echt scherm.

### 11.2 isTrusted=true noodzakelijk

ETV's jQuery-handlers filteren synthetische events (`isTrusted=false`) weg. Dat geldt voor:
- **Spelers-suggesties** â€” ActionChains.move_to_element + click is nodig
- **Daypart-elementen** â€” idem
- **Tijdslot-cellen** â€” idem

`dispatchEvent` / `el.click()` via JS hebben `isTrusted=false` en worden genegeerd. UI lijkt te updaten maar server-side komt het niet door.

### 11.3 GitHub Actions cron is onbetrouwbaar

Documented limitation: scheduled workflows kunnen volledig overgeslagen worden bij hoge load, en hebben vooral kort na toevoeging vertraging (uren tot dagen). Bewezen: de eerste productie-nacht (29-05 06:55 NL) vuurde de cron simpelweg niet, ook al was de workflow `state: active`.

**Oplossing:** externe scheduler ([cron-job.org](https://cron-job.org)) die via de GitHub API een `workflow_dispatch` event verstuurt. GitHub honoreert workflow_dispatch events betrouwbaar.

### 11.4 Recent mee gespeeld race condition

De `_voeg_speler_toe()` had ooit een brede XPath-fallback `//*[contains(., 'achternaam') and not(self::input)...]`. Die matchte ook elementen in het "Recent mee gespeeld" paneel â€” voor spelers die je recent had gereserveerd stond hun naam alay zichtbaar op de spelers-pagina vÃ³Ã³r de typeahead Ã¼berhaupt loaded.

Resultaat: WebDriverWait zag direct een "match", kandidaten-loop pakte het Recent-element, ActionChains klikte de naam-`<span>` â€” en omdat dat element een ANDERE click-handler heeft (UI-only update zonder server-AJAX) registreerde de speler nooit server-side. Bij bevestig zei de server dan terecht "Joris niet genoeg spelers".

**Symptomen:** spelers wel verified bij click, maar bij bevestig "niet genoeg spelers". Intermittent â€” afhankelijk van of Recent-paneel die speler bevat Ã©n of typeahead snel genoeg rendert om de specifieke selector eerder match te krijgen.

**Fix (commit 35111db):** brede fallback verwijderd. Alleen `role=option`, `<li>` en `<div class=player/suggestion/result/item>`. Mocht ETV ooit een onbekende suggestie-container gaan gebruiken, dan faalt de speler-add expliciet ipv een verkeerd element te klikken.

### 11.5 Foute speler-selectie bug (Christel-incident)

Op 28-05 om 07:11 NL selecteerde het oude script per ongeluk "Christel Beckmann Asselman" ipv "Chris van Waardenburg". Oorzaak: de XPath `contains(., 'Waardenburg')` matchte een **container-element** met meerdere namen erin: `Spelers\nChristel Beckmann Asselman\nChris Pieterse\nChris van Waardenburg`. Het script klikte het eerste klikbare in die container = Christel.

**Fix (commit 6d881f5):** strikte text-equality. De tekst van het te klikken element MOET genormaliseerd exact gelijk zijn aan een geaccepteerde naamvorm. Een container met meerdere namen wordt afgewezen omdat zijn innerText niet exact "Chris van Waardenburg" is.

### 11.6 Push-race-conditions

Vier bronnen pushen naar main: jij, GitHub Actions bot (boek_baan.py's `_zet_in_wachtrij`), verwerk_wachtrij workflow, lees_reserveringen.py. Conflicting pushes triggerden eerder een `git push rejected (fetch first)`-fout.

**Fix (commit 2ba1274):** alle push-plekken hebben nu een retry-loop:
```bash
for i in 1 2 3 4 5; do
  git pull --rebase origin main || true
  if git push; then exit 0; fi
  sleep $i
done
```

### 11.7 Cron-vroege start vs boekvenster-timing

Probleem (oorspronkelijk): cron triggert om 06:50, prep duurt 5 min, dan wait-at-top tot 07:01, dan bevestig om 07:04 â€” te laat, slot mogelijk al weg.

**Fix v1 (commit 103493b):** wait-at-top verwijderd; sleep verschoven naar VLAK VOOR bevestig-klik. Prep loopt tijdens de wachttijd.

### 11.8 Boekvenster geldt vanaf dag-keuze, niet alleen bevestig

Vervolg op 11.7. Run #63 (cron 30-05 06:50 NL voor 01-06) bewees dat ETV's server al de **daypart-selectie zelf** weigert vÃ³Ã³r 07:00:

```
06:52:17 Volgende methode: requestSubmit
06:52:32 WARNING Geen herkenbare navigatie binnen 15s
06:52:32 WARNING Geen navigatie. URL: ReservationsDay
```

3Ã— kies_dag retry, allemaal hetzelfde patroon. Mijn aanname dat alleen `bevestig` na 07:00 hoeft was fout â€” het hele blok kies_dag â†’ kies_baan_en_tijd â†’ bevestig moet nÃ¡ de slot-opening lopen.

**Fix v2 (commit 6744516):** sleep verschoven naar VLAK VOOR kies_dag. Login + spelers gebeurt tijdens de wachttijd (geen slot-validatie daar). Vanaf 07:01 NL doet het script kies_dag â†’ kies_baan_en_tijd â†’ bevestig in Ã©Ã©n doorloop. Bevestig valt nu rond 07:02-03 â€” iets later dan 07:01 sharp, maar wel werkend.

### 11.9 ETV "1 actieve reservering"-rule (vermoeden, niet definitief bewezen)

ETV lijkt impliciet geen 2e actieve reservering toe te staan per lid. Symptoom: bij booking-attempt terwijl een andere reservering actief is, kreeg het script terug-redirect naar spelers-pagina. Niet 100% gevalideerd; de Recent-paneel-bug verklaarde mogelijk een aantal van die failures.

### 11.10 Spelers selecteren via UUID (data-id)

Niet eigenlijk een valkuil maar een sleutel-inzicht uit een lange dag debugging (29-05).

**De juiste manier om een speler te selecteren** is via het `data-id` attribuut van het `.addPlayer`-element. ETV's HTML:

```html
<div class="card-body addPlayer" data-id="4f14518b-3003-4573-ac95-b4ec0346fa20">
  Chris van Waardenburg
</div>
```

Na succesvolle add:

```html
<div id="youPlayWith">
  <li>
    <h6>Chris van Waardenburg</h6>
    <a class="removePlayer" data-id="4f14518b-3003-4573-ac95-b4ec0346fa20">Ã—</a>
  </li>
</div>
```

**Werkwijze (commit 534fa39 / cf31c3c):**

1. Type zoekterm
2. Vind `.addPlayer[data-id]` waarvan innerText EXACT gelijk is aan een geaccepteerde naamvorm
3. Onthoud de `data-id` (string), NIET het element-ref
4. Vind het element vers via `driver.find_element(By.CSS_SELECTOR, '.addPlayer[data-id="UUID"]')` â€” ETV's typeahead refresht de DOM binnen ~300ms, dus refs uit `execute_script` verstaleren onmiddellijk
5. ActionChains click
6. Verifieer: `#youPlayWith` MOET een element bevatten met DIE SPECIFIEKE data-id

**Waarom data-id verificatie:** visible name kan misleiden (HTML toonde dubbele spaties zoals `"Christel  Beckmann Asselman"`), maar UUIDs liegen niet. Als de data-id na de click niet in `#youPlayWith` staat, weten we 100% zeker dat de juiste speler NIET is toegevoegd â€” abort dan ipv doorgaan.

### 11.11 Race-conditie: andere boeker pakt de baan tussen kies en bevestig

Vlak na 07:00 NL hangen meerdere clubleden tegelijk op de portal. Het venster tussen `kies_baan_en_tijd` en `bevestig` is ~1-2 sec, en ETV's server accepteert in die seconden gewoon de eerste boeker die een specifiek tijdslot claimt. De latere boeker krijgt op zijn `SaveReservation`-POST een melding zoals "niet gevonden" / "al gereserveerd" / "reeds geboekt" / "niet meer beschikbaar".

**Tot commit 1675acf**: dit was een hard fail â€” script crashte met "âŒ Bevestigen mislukt". Frustrerend want er waren typisch nog 5 andere padelbanen vrij op dezelfde tijd.

**Sinds 1675acf / 679f0de**: `bevestig()` retourneert 3-state (`'OK'` / `'BEZET'` / `'FOUT'`) en `main()` heeft een retry-loop die bij BEZET terugnavigeert naar `/me/ReservationsCourt`, een `driver.refresh()` doet voor verse DOM, en `kies_baan_en_tijd` opnieuw aanroept. Volledige uitleg in [sectie 8 â†’ bevestig + BEZET-retry](#bevestig--bezet-retry-race-conditie-tussen-kies-en-bevestig).

**Belangrijk inzicht**: ETV's baan-keuze pagina toont een bezette tijdcel simpelweg niet meer na de refresh. Dat bespaart bookkeeping â€” geen aparte uitsluit-lijst van banen nodig. `kies_baan_en_tijd` itereert al voor elke voorkeur-tijd over alle padelbanen die op dat moment in de DOM staan en pakt de eerstvrije; pas als alle 6 padelbanen op die tijd weg zijn valt 'ie terug op alternatieve tijden (14:30, 15:30, etc.). De DOM IS de filter.

**Detectie-patronen** (case-insensitive substring-match op AJAX-response):
- `"niet gevonden"`
- `"not found"`
- `"al gereserveerd"`
- `"reeds geboekt"`
- `"niet meer beschikbaar"`

Komt een nieuwe ETV-versie met andere formulering: voeg het patroon toe in beide checks in `bevestig()` (Poging A en Poging B).

### 11.12 Typeahead substring-matches voegen mystery-spelers toe (Daniel-bug)

Run #68 + #69 (31-05) faalden allebei op het toevoegen van Johan Janssen. Diagnose:

- Zoekterm voor speler 2 was **"Daniel Enderink"**
- ETV's typeahead toonde meerdere cards in de dropdown: Daniel Enderink + andere namen met "Danâ€¦"-prefix of "Daniel"-substring:
  - Run #68 mystery-speler: **Danse Cleij** ("Danâ€¦" prefix)
  - Run #69 mystery-speler: **Ellen Daniels** ("â€¦Danielâ€¦" substring)
- Het script vond Daniel correct via `innerText === 'Daniel Enderink'` (exact match) en klikte 'm via ActionChains. Daniel kwam netjes in `#youPlayWith`.
- **MAAR**: Ã³Ã³k de mystery-speler verscheen in `#youPlayWith` zonder dat het script ernaar verwijst (log bevat geen klik op die data-id). Vermoedelijk via een hover-event tijdens `ActionChains.move_to_element()` of via een focus-event in de `CTRL+A`/`DELETE` flow voor de volgende speler.
- In run #69 was `#youPlayWith` daardoor al vol met **Daniel + Ellen + Toine** vÃ³Ã³r Johan aan de beurt kwam. ETV weigerde toen Johan toe te voegen (max 4 spelers incl. Joris zelf).

Bij Joris's handmatige boeking met dezelfde spelers waren er GEEN mystery-toevoegingen. Bevestiging dat de bug puur in de Selenium-flow zit, niet in ETV's gedrag.

**Fix:** defensieve scan-en-verwijder. Na elke succesvolle speler-add scant `_ruim_onverwachte_spelers_op()` `#youPlayWith` op data-ids; alles wat NIET in de set `{eerder toegevoegde + huidige}` zit wordt verwijderd via een klik op `a.removePlayer[data-id="..."]`. Zelfde patroon als de toevoeg-klik: jQuery `.trigger('click')` met DOM-`.click()` als fallback.

De fix wordt Ã³Ã³k aan het begin van `voeg_spelers_toe()` aangeroepen met een lege set â€” dat ruimt stale leftover state uit een vorige gecrashte booking-poging op.

---

## 12. Wijzigingen aanbrengen

### Speler 1 wijzigen

In `boek_baan.py`:
```python
SPELER1 = "Joris van den Broek"
```

### Standaard tijd / tijdsbereik

In `docs/index.html`:
```javascript
tijdEl.value = '15:00';   // standaard
```

In `boek_baan.py` `genereer_tijden()`:
```python
vroegst = datetime.strptime("08:00", "%H:%M")
laatst  = datetime.strptime("22:00", "%H:%M")
```

### Boekvenster-timing wijzigen (bv. 07:00 ipv 07:01)

In `boek_baan.py`, in `main()` net voor de `kies_dag` call:
```python
doel_window_open = reserveringsdatum.replace(hour=7, minute=1, ...)
                                                  â†‘
```

### Cron-tijd wijzigen

In cron-job.org â†’ cronjob â†’ tab Schedule. **Niet** in `verwerk_wachtrij.yml` editen (die schedule is een fallback voor als cron-job.org down is).

### Nieuwe versie van de PWA uitrollen

1. Wijzig `docs/index.html`
2. Bump `CACHE` in `docs/sw.js`:
   ```javascript
   const CACHE = 'padel-v17';   // was v16
   ```
3. Commit + push. GitHub Pages serveert binnen 1-3 min.

### Cron-job.org PAT vernieuwen

Bij PAT-expiry: nieuwe classic PAT met `workflow` scope â†’ cron-job.org â†’ Headers â†’ `Authorization` waarde aanpassen â†’ Save â†’ Test run.

### Site-redesign van ETV Volley

Bij grote HTML-veranderingen kunnen stappen falen. Diagnose:

| Screenshot | Moment |
|------------|--------|
| `01_login_pagina.png` | Loginpagina geladen |
| `02_na_login.png` | Direct na inloggen |
| `02b_login_mislukt.png` | Alleen als wachtwoordveld nog zichtbaar |
| `03_reserveer_pagina.png` | Reserveringen-overzicht |
| `04_na_afhangen_klik.png` | Na klikken "Baan afhangen" |
| `05_spelers_pagina.png` | Spelers-pagina geladen |
| `05b_zoek_*` | Tijdens zoeken speler 2/3/4 |
| `05c_niet_gevonden_*` | Geen exacte match (strict matching faalde) |
| `05d_niet_geverifieerd_*` | Klik gelukt maar speler niet op pagina zichtbaar |
| `06_spelers_toegevoegd.png` | Na toevoegen alle spelers |
| `07_dag_pagina.png` | Dag-keuze pagina |
| `08_dag_geselecteerd_poging{N}.png` | Per kies_dag-poging |
| `terug_naar_spelers_poging{N}.png` | Back-redirect naar spelers (server weigerde dagdeel) |
| `09_baan_pagina.png` | Baan/tijdslot-pagina |
| `10_baan_geselecteerd.png` | Na tijdslot-klik |
| `11_bevestig_pagina.png` | Confirm-pagina |
| `12_na_bevestiging.png` | Na bevestig-klik |

### Python-dependencies updaten

Bij gewijzigde versies in de drie boek-workflows:
```yaml
pip install undetected-chromedriver selenium \
            google-api-python-client google-auth
```

Geen `requirements.txt` â€” pip kiest de versies. Bij Chrome-update kan UC tijdelijk breken; check de `version_main`-detectie in `chrome_major_versie()`.

---

## 13. Toekomstige features â€” multi-user setup

**Status: niet geÃ¯mplementeerd. Geplande feature voor wanneer meerdere ETV-leden de tool willen gebruiken.**

Op dit moment is alle code gericht op Ã©Ã©n account (Joris's KNLTB-credentials in `secrets.ETVVOLLEY_BONDSNUMMER` + `SPELER1 = "Joris van den Broek"` hardcoded). Onderstaand plan maakt dezelfde repo bruikbaar voor meerdere ETV-leden zonder fork.

### 13.1 Architectuur

Per-user GitHub Secrets in dezelfde repo (`joris-vandenBroek/knltb-autoboek`):

| Secret | Voor |
|---|---|
| `ETVVOLLEY_BONDSNUMMER_JORIS` / `ETVVOLLEY_WACHTWOORD_JORIS` | Joris's KNLTB-login |
| `ETVVOLLEY_BONDSNUMMER_TOINE` / `ETVVOLLEY_WACHTWOORD_TOINE` | Toine's KNLTB-login |
| `GOOGLE_CALENDAR_CREDENTIALS` | shared service-account JSON (Ã©Ã©n voor alle users) |
| `GOOGLE_CALENDAR_ID_JORIS` | Joris's agenda-ID |
| `GOOGLE_CALENDAR_ID_TOINE` | Toine's agenda-ID (optioneel) |

Nieuwe gebruikers vertellen hun KNLTB-credentials Ã©Ã©nmalig aan de repo-eigenaar. Na opslaan als GitHub Secret zijn ze write-only â€” niet meer terug te lezen via de UI.

### 13.2 Workflow-wijzigingen

`boek.yml`, `beheer_reserveringen.yml`, `verwerk_wachtrij.yml` krijgen een `gebruiker` input + conditional env-vars:

```yaml
on:
  workflow_dispatch:
    inputs:
      gebruiker:
        description: 'Account-eigenaar (joris/toine)'
        default: 'joris'
        required: true
      datum:    { required: true }
      tijd:     { required: true }
      speler2:  { required: true }
      speler3:  { required: true }
      speler4:  { required: true }

jobs:
  boek:
    runs-on: ubuntu-latest
    env:
      ETVVOLLEY_BONDSNUMMER: ${{ inputs.gebruiker == 'toine' && secrets.ETVVOLLEY_BONDSNUMMER_TOINE || secrets.ETVVOLLEY_BONDSNUMMER_JORIS }}
      ETVVOLLEY_WACHTWOORD:  ${{ inputs.gebruiker == 'toine' && secrets.ETVVOLLEY_WACHTWOORD_TOINE  || secrets.ETVVOLLEY_WACHTWOORD_JORIS }}
      SPELER1_NAAM:      ${{ inputs.gebruiker == 'toine' && 'Toine Aanraad' || 'Joris van den Broek' }}
      GOOGLE_CALENDAR_CREDENTIALS: ${{ secrets.GOOGLE_CALENDAR_CREDENTIALS }}
      GOOGLE_CALENDAR_ID: ${{ inputs.gebruiker == 'toine' && secrets.GOOGLE_CALENDAR_ID_TOINE || secrets.GOOGLE_CALENDAR_ID_JORIS }}
```

### 13.3 Python-scripts

`boek_baan.py` en `lees_reserveringen.py` â€” Ã©Ã©n regel verandert:

```python
SPELER1 = os.environ.get("SPELER1_NAAM", "Joris van den Broek")
```

Rest van de logica is sinds de data-id refactor (commit 534fa39) volledig user-agnostic â€” geen hardcoded namen meer in verificatie of click-targeting.

`_zet_in_wachtrij()` en alle plekken die naar `reserveringen.json` of `wachtrij/` schrijven moeten een gebruiker-arg meekrijgen â€” paden worden per-user.

### 13.4 Data-isolatie

| Was | Wordt |
|---|---|
| `reserveringen.json` | `reserveringen_joris.json` + `reserveringen_toine.json` |
| `wachtrij/<datum>_<tijd>.json` | `wachtrij/joris/<datum>_<tijd>.json` + `wachtrij/toine/<datum>_<tijd>.json` |
| `leden.json` | Houden zoals nu (Ã©Ã©n ledenlijst voor de hele club) |

`verwerk_wachtrij.yml` cron-loopje moet door beide user-folders heen lopen en voor elk item de juiste `gebruiker` als input doorgeven aan `boek.yml`.

### 13.5 PWA-aanpassingen

- **Gebruiker-selector** (dropdown) bovenaan of in âš™ï¸
- `localStorage.knltb_gebruiker` opslaan
- `RESERV_URL` dynamisch: `reserveringen_${gebruiker}.json`
- `WACHTRIJ_API` dynamisch: `contents/wachtrij/${gebruiker}`
- `workflow_dispatch` body: voeg `inputs.gebruiker` toe
- Per-user state behouden (spelers-presets in localStorage per user keyed)

### 13.6 Google Calendar setup voor extra gebruiker (Optie A â€” shared service account, aanbevolen)

Het bestaande service-account kan voor meerdere agendas tegelijk schrijven. Nieuwe gebruiker doet zelf:

1. Google Agenda â†’ naast eigen agenda â‹® â†’ **Instellingen en delen**
2. Onder "Personen met toegang" â†’ **Personen uitnodigen**
3. Plak het service-account email (vind je in de JSON onder `"client_email"`, bv. `padel-boeker@xxx.iam.gserviceaccount.com`)
4. Rol: **"Afspraken beheren"**
5. Geef de eigen calendar-ID door aan repo-eigenaar (gmail-adres of `primary`)

Repo-eigenaar voegt `GOOGLE_CALENDAR_ID_<USER>` als secret toe. Klaar.

**Voordeel boven Optie B (eigen service account per user):** ~2 min ipv ~10 min setup; Ã©Ã©n Google Cloud project te onderhouden.

### 13.7 Cron-job.org

EÃ©n PAT van repo-eigenaar (met `workflow` scope) is genoeg voor alle gebruikers. De cron triggert `verwerk_wachtrij` zonder gebruiker-arg; de workflow loopt zelf door beide user-folders en triggert de juiste `boek.yml`-runs.

### 13.8 Effort-inschatting

| Onderdeel | Tijd |
|---|---|
| 3 workflow-files (boek/beheer/verwerk_wachtrij) â€” input + conditional env | 15 min |
| `boek_baan.py` + `lees_reserveringen.py` parametrize | 15 min |
| `verwerk_wachtrij.yml` per-user loop | 10 min |
| File-rename `reserveringen.json` â†’ `reserveringen_joris.json` + nieuwe lege voor extra users | 5 min |
| Wachtrij-folder restructure | 5 min |
| PWA gebruiker-selector + dynamic URLs | 15 min |
| Docs (README + knltb-autoboek.md) | 10 min |
| Per nieuwe gebruiker: KNLTB-secrets + Google Calendar-deling | ~5 min |
| **Totaal eenmalige refactor** | **~1.5 uur** |

### 13.9 Privacy + trust-model

- KNLTB-credentials: na opslaan als Secret zijn ze write-only. Zelfs de repo-eigenaar kan ze niet meer terug-lezen. Vertrouwen is alleen nodig bij eenmalige invoer.
- Service-account heeft enkel toegang tot het delen-domein van iedere agenda (alleen padel-events maken/verwijderen), niet bredere agenda-leesrechten.
- PAT voor cron-job.org: Ã©Ã©n pat van eigenaar volstaat. Geen per-user PAT nodig.
- Workflows: gebruikt secrets via masking â€” credentials worden in Action-logs vervangen door `***`.

Geen serieuze blast-radius bij compromittering (geen financiÃ«le koppeling, geen persoonlijke data buiten ETV-baanreserveringen).


---

## 14. Operationele veiligheidsnetten

### 14.1 Concurrency-groepen

Alle 3 workflows (`boek.yml`, `beheer_reserveringen.yml`, `verwerk_wachtrij.yml`) hebben:

```yaml
concurrency:
  group: knltb-account-joris
  cancel-in-progress: false
```

**Waarom:** twee gelijktijdige Selenium-sessies tegen Ã©Ã©n ETV-account is sowieso vragen om problemen (race op `reserveringen.json` commit, ETV "1 actieve reservering"-vermoeden, dubbele agenda-events). De groep serialiseert runs op het account-niveau. `cancel-in-progress: false` zorgt dat een lopende boeking nooit halverwege wordt afgekapt door een nieuwe PWA-tap.

Bij toekomstige multi-user wordt `group: knltb-account-${inputs.gebruiker}` zodat Joris en Toine parallel kunnen draaien (verschillende ETV-accounts) maar elk zelf nooit twee tegelijk.

### 14.2 Auto-issue bij failure

Elke workflow heeft een `if: failure()` step die via `gh issue create` een GitHub Issue opent met:
- Run-link (naar Actions logs)
- Context (datum/tijd/spelers voor boek, actie voor beheer)
- Label `auto-failure,<bron>` voor filtering

Per failure Ã©Ã©n issue. Je krijgt de standaard GitHub issue-mail; geen extra secret/webhook nodig.

### 14.3 Healthchecks.io dead-man's-switch (optioneel)

Als secret `HEALTHCHECK_PING_URL` is gezet (formaat `https://hc-ping.com/<uuid>`), pingt `verwerk_wachtrij.yml`:
- `/start` bij begin van elke run
- *(success URL)* als alle stappen ok zijn
- `/fail` als iets faalt

Setup (~3 min): account op [healthchecks.io](https://healthchecks.io) â†’ Add Check â†’ period 26 hours (cron 24u + buffer) â†’ notifications email/Slack/etc â†’ kopieer ping URL als Secret.

**Voordeel:** ook bij compleet stille failures (cron-job.org account opgezegd, PAT verlopen â†’ 401, GitHub Actions globale outage) krijg je binnen 24u een alert. Zonder dit weet je pas dat het fout zit als een wachtrij-boeking gemist wordt.

### 14.4 Wachtrij-TTL

`verwerk_wachtrij.yml` parsed het `ingediend`-veld van elk wachtrij-bestand. Items ouder dan **60 dagen** worden zonder boeking-trigger verwijderd. Voorkomt dat een half-vergeten plan van maanden terug spontaan een boeking creÃ«ert. Log toont per run: `Aantal verwerkt: N | Verlopen opgeruimd: M`.

### 14.5 Dry-run modus

`boek_baan.py --dry-run`: loopt door alle stappen (login + spelers + dag + baan + Volgende naar Confirm + zoek Bevestig-knop) maar slaat de daadwerkelijke `jQuery.trigger('click')` op de Bevestig-knop over. Returnt `'OK'` en `exit(0)` vÃ³Ã³r verificatie / agenda / `reserveringen.json` update â€” geen state-pollution.

Via PWA: amber ðŸ§ª toggle boven de Reserveer-knop. Bij activering wijzigt de knop naar oranje + label "ðŸ§ª Dry-run baan reserveren" voor visuele bevestiging. State persisteert NIET in localStorage â€” elke tap is een bewuste keuze.

Workflow: `boek.yml` heeft input `dry_run` (choice: true/false, default false) die wordt doorgegeven als `--dry-run` flag. Handig voor handmatige tests via Actions-UI.

**Use case:** voor potentieel-problematische speler-combo's (substring-overlap zoals Daniel + Brugmans + Toine) eerst dry-run starten. Bij groen log â†’ echte boeking. Bij rood log â†’ verwacht failure pattern, fix code zonder echte reservering aan te maken.

### 14.6 PAT-expiry waarschuwing (PWA)

PWA toont badge op âš™ï¸-icoon:
- amber (`#f59e0b`) bij 8-30 dagen tot verloop
- rood bij 0-7 dagen
- pulsende donkerrood `!` na verloop + harde error-toast

Setup: in PAT-sheet vul de verloopdatum in (optioneel veld onder het PAT-veld zelf). Bewaard in `localStorage` als `knltb_pat_verloopt` (ISO date string). Pure client-side check â€” geen GitHub API-call nodig.

### 14.7 Spelers 2-poging retry

`voeg_spelers_toe()` doet per speler maximaal 2 pogingen. Bij fail van `_voeg_speler_toe()`: `driver.refresh()` + retry. De defensieve cleanup (zie 11.12) zorgt dat eerder-toegevoegde spelers de refresh overleven.

Gebruikssituatie: Ã©Ã©n enkele netwerk-glitch of ETV-typeahead-vertraging crasht niet meer de hele booking-flow.

### 14.8 Gedeelde ETV-login

`etv_common.py` bevat de canonieke `login()` functie, gebruikt door `lees_reserveringen.py` en `haal_leden_op.py`. `boek_baan.py` heeft (voorlopig) nog z'n eigen `login()` â€” staat een TODO bij om over te zetten zodra de huidige cron-flow stabiel is bewezen.

Vermijdt drift: een anti-bot fix in Ã©Ã©n script bleef voorheen achter in de andere twee.

### 14.9 Stale-while-revalidate voor Mijn reserveringen

Probleem dat dit oplost: `reserveringen.json` wordt alleen bijgewerkt door
expliciete acties (Verversen-knop, annulering, auto-boeking). Handmatige
boekingen op de ETV-site staan dus NIET in de cache tot iemand het script
triggert. Gebruiker zag bij PWA-open een stale lijst en moest handmatig
op Verversen klikken.

**Patroon (in `docs/index.html`):**

1. Bij PWA-open / tab-terugkomst: render de gecachte JSON direct
   (zelfde markup als voorheen + 'Bijgewerkt: DD-MM-YYYY' footer)
2. Bereken ouderdom via `data.bijgewerkt` timestamp
3. Als ouderdom > **15 minuten** (constant `RESERV_STALE_MINUTES`)
   en PAT is aanwezig: `autoVerversReserveringen()`
4. Achtergrondrefresh:
   - Triggert `beheer_reserveringen.yml` via workflow_dispatch
   - Toont kleine blauwe pill onder de lijst: 'ðŸ”„ Aan het verversenâ€¦'
   - Pol elke 30s vanaf t+60s: vergelijk `data.bijgewerkt` met
     timestamp van vÃ³Ã³r de trigger; bij verschil â†’ re-render + pill weg
   - Time-out na 3 min als de workflow nooit completion-signaal geeft
5. Concurrency: `_autoVerversBezig` flag voorkomt dubbele triggers
   van back-to-back PWA-opens

`visibilitychange` event-listener: wanneer de tab van hidden â†’ visible
gaat, opnieuw `laadReserveringen()` (en `laadWachtrij()`). Dekt mobile
multitasking: app weer naar voren â†’ vers data.

**Trade-off:** ~1.5 min workflow draait elke 15 min dat je de PWA opent.
Bij intensief PWA-gebruik kan dit oplopen, maar de concurrency-group
('knltb-account-joris' uit 14.1) serialiseert runs zodat 't nooit
parallel met een boeking loopt.


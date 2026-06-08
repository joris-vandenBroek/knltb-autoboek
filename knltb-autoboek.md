# knltb-autoboek -- Volledige documentatie

**GitHub-repository:** `joris-vandenBroek/knltb-autoboek`  
**Doel:** Automatisch een padelbaan reserveren bij ETV Volley via de KNLTB-ledenportal, aangestuurd via een PWA op de telefoon, inclusief Google Agenda-integratie en wachtrij voor toekomstige reserveringen.

---

## Inhoudsopgave

1. [Hoe werkt het in grote lijnen](#1-hoe-werkt-het-in-grote-lijnen)
2. [Repository-structuur](#2-repository-structuur)
3. [Benodigde GitHub Secrets](#3-benodigde-github-secrets)
4. [Externe cron-trigger via cron-job.org](#4-externe-cron-trigger-via-cron-joborg)
5. [PWA-frontend -- docs/index.html](#5-pwa-frontend--docsindexhtml)
6. [Service Worker -- docs/sw.js](#6-service-worker--docsswjs)
7. [Workflows](#7-workflows)
8. [boek_baan.py -- stap voor stap](#8-boek_baanpy--stap-voor-stap)
9. [lees_reserveringen.py -- reserveringen + annuleren](#9-lees_reserveringenpy--reserveringen--annuleren)
10. [haal_leden_op.py -- ledenlijst scrapen](#10-haal_leden_oppy--ledenlijst-scrapen)
11. [haal_padel_sterktes.py -- padel speelsterktes ophalen](#11-haal_padel_sterktesppy--padel-speelsterktes-ophalen)
12. [Technische valkuilen en beslissingen](#12-technische-valkuilen-en-beslissingen)
13. [Wijzigingen aanbrengen](#13-wijzigingen-aanbrengen)
14. [Toekomstige features -- multi-user setup](#14-toekomstige-features--multi-user-setup)
15. [Operationele veiligheidsnetten](#15-operationele-veiligheidsnetten)

---

## 1. Hoe werkt het in grote lijnen

```
Gebruiker (telefoon)
        |  tikt op "Baan reserveren" in de PWA
        v
docs/index.html (GitHub Pages PWA)
        |  POST naar GitHub Actions API (met PAT-token)
        v
.github/workflows/boek.yml
        |  Start Python-script met datum/tijd/spelers
        v
boek_baan.py
        |  IF speeldatum > dag+2:
        |     -> schrijf wachtrij/<datum>_<tijd>.json + commit/push
        |  ELSE:
        |     -> login + spelers + (wacht tot 07:01 NL) + dag + baan + bevestig
        v
Google Agenda  (via Service Account, optioneel)
        v
Klaar -- e-mail van ETV Volley + agenda-event

+----------------------------------------------------------+
| Voor wachtrij-items (dag+3 en verder):                   |
|                                                          |
| cron-job.org (06:50 NL dagelijks)                        |
|     |  POST naar GitHub Actions API                      |
|     v                                                    |
| verwerk_wachtrij.yml                                     |
|     |  Voor elk wachtrij-bestand met                     |
|     |  reserveringsdatum == vandaag:                     |
|     |     -> triggert boek.yml met die inputs            |
|     v                                                    |
| boek.yml -> boek_baan.py -> dag-keuze vanaf 07:01 NL    |
+----------------------------------------------------------+
```

De **ledenlijst** (`leden.json`) wordt los bijgehouden via `haal_leden_op.yml` (wekelijks of handmatig). Na een ledenlijst-refresh worden automatisch de **padel speelsterktes** opgehaald via `haal_padel_sterktes.yml`. Gebruikt door de PWA voor de speler-dropdowns.

De **actieve reserveringen** (`reserveringen.json`) worden bijgehouden via `lees_reserveringen.py` + `beheer_reserveringen.yml`, getriggerd vanuit de PWA bij Verversen of Annuleren.

---

## 2. Repository-structuur

```
knltb-autoboek/
|-- boek_baan.py                 # Hoofdscript: Selenium-reservering + wachtrij
|-- lees_reserveringen.py        # Scrape + annuleer actieve reserveringen
|-- haal_leden_op.py             # Scrape de ledenlijst -> leden.json
|-- haal_padel_sterktes.py       # Haal padel speelsterktes -> leden.json
|-- leden.json                   # Cache van alle ETV-leden met padel sterktes (~977 leden)
|-- reserveringen.json           # Cache van actieve reserveringen
|-- wachtrij/                    # Reserveringen voor speeldatums > dag+2
|   |-- .gitkeep
|   \-- YYYY-MM-DD_HHMM.json     # Per ingeplande reservering
|-- docs/                        # PWA (GitHub Pages source)
|   |-- index.html               # Single-page app
|   |-- sw.js                    # Service Worker (cache versioning)
|   |-- manifest.json            # PWA-manifest
|   \-- logo.png + icon-192/512.png
\-- .github/workflows/
    |-- boek.yml                 # Voer een reservering uit
    |-- verwerk_wachtrij.yml     # Verwerk wachtrij (door cron-job.org getriggerd)
    |-- beheer_reserveringen.yml # Scrape of annuleer reservering (vanuit PWA)
    |-- haal_leden_op.yml        # Ledenlijst-refresh (maandag 07:00) + trigger padel sterktes
    \-- haal_padel_sterktes.yml  # Padel speelsterktes ophalen via mijnknltb.toernooi.nl
```

GitHub Pages is ingesteld op de `docs/`-map van de `main`-branch. De PWA is bereikbaar via `https://joris-vandenbroek.github.io/knltb-autoboek/`.

---

## 3. Benodigde GitHub Secrets

In te stellen via **GitHub -> Repository -> Settings -> Secrets and variables -> Actions**:

### ETV Volley (etv-volley.nl)

| Secret | Inhoud |
|--------|--------|
| `ETVVOLLEY_BONDSNUMMER` | Gebruikersnaam voor etv-volley.nl |
| `ETVVOLLEY_WACHTWOORD` | Wachtwoord voor etv-volley.nl |

### mijnKNLTB (mijnknltb.toernooi.nl)

| Secret | Inhoud |
|--------|--------|
| `KNLTB_LOGINNAAM` | Gebruikersnaam voor mijnknltb.toernooi.nl |
| `KNLTB_WACHTWOORD` | Wachtwoord voor mijnknltb.toernooi.nl |

### Overig

| Secret | Inhoud |
|--------|--------|
| `GOOGLE_CALENDAR_CREDENTIALS` | Volledige JSON-inhoud van het Service Account-sleutelbestand |
| `GOOGLE_CALENDAR_ID` | Agenda-ID (bijv. `primary` of e-mailadres) |
| `HEALTHCHECK_PING_URL` *(optioneel)* | Healthchecks.io check URL voor dead-man's-switch (zie sectie 15) |

Het **GitHub Personal Access Token (PAT)** wordt *niet* als Secret opgeslagen, maar:
- **In de PWA** in `localStorage` (sleutel `knltb_pat`) voor PWA-triggers (workflow_dispatch)
- **In cron-job.org** in een header voor de dagelijkse wachtrij-trigger

Beide PATs hebben minimaal `workflow` scope nodig (classic) of `Actions: Read and write` op deze repo (fine-grained).

---

## 4. Externe cron-trigger via cron-job.org

**Waarom extern?** GitHub Actions' eigen `schedule:`-triggers zijn best-effort en kunnen volledig overgeslagen worden, vooral bij nieuwe workflows of tijdens hoge load. Dit gebeurde inderdaad op de eerste productie-nacht: de cron `'55 4 * * *'` in `verwerk_wachtrij.yml` vuurde simpelweg niet, ook al was de workflow `active`. cron-job.org is een externe service die wel deterministisch op tijd vuurt.

### Setup

1. **Classic PAT aanmaken** op [github.com/settings/tokens/new](https://github.com/settings/tokens/new):
   - Scope: alleen `workflow` (geeft automatisch `repo`-rechten)
   - Expiration: bv. 1 jaar
2. **Account** op [cron-job.org](https://cron-job.org) -> Create cronjob:
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
3. **Test run** -> moet 204 No Content geven

### Trade-offs

- Betrouwbaar (vuurt op tijd)
- Heeft notificaties bij failure
- Externe service heeft je PAT
- cron-job.org gratis tier heeft een limiet (~1 trigger/min, ruim voldoende voor dagelijks)

---

## 5. PWA-frontend -- docs/index.html

Een HTML-bestand zonder frameworks. Werkt als installeerbare PWA op iPhone en Android. Sectie-volgorde:

1. **Header** met ETV Volley-logo + tandwiel-knop voor PAT
2. **Wanneer** -- datumkiezer + tijdkeuze (08:00-21:30, stappen van 30 min, standaard 15:00)
3. **Medespelers** -- 3 dropdowns met zoekfilter (PrimeFaces-stijl)
4. **Mijn reserveringen** -- actieve reserveringen + annuleren per item
5. **Ingeplande reserveringen** -- wachtrij + verwijderen per item
6. **Baan reserveren** -- vast onderaan, triggert workflow

### Mobile sizing

Basis font-size `22px` (op viewport < 380px: `20px`). Velden minimaal 58px hoog, knoppen 76px. Doel: comfortabel tappen op midrange telefoons (S10+, iPhone 12, etc.).

### Date-picker click-fix

De native `<input type="date">` ligt als transparante overlay op de visuele knop. CSS-regel `pointer-events: none` op `.date-native` zorgt dat het hele veld klikbaar is. De JS-handler op `.date-picker-btn` roept `showPicker()` aan.

### Mijn reserveringen (PWA-card)

```javascript
const RESERV_URL = `https://raw.githubusercontent.com/${REPO}/main/reserveringen.json`;
```

- **Laden op page open:** fetch `reserveringen.json` van GitHub raw, render lijst.
- **Verversen:** workflow_dispatch op `beheer_reserveringen.yml` met `cancel_id=""` -> script logt in, scrape, commit/push update naar `reserveringen.json`. PWA pollt 4x tussen 90s en 180s om nieuwe state te tonen.
- **Annuleer-knop per item:** confirm-dialoog -> workflow_dispatch met `cancel_id="YYYY-MM-DD_HHMM_baan-slug"` -> script annuleert op ETV-site + verwijdert agenda-event + ververst lijst.

### Ingeplande reserveringen (wachtrij, PWA-card)

```javascript
const WACHTRIJ_API = `https://api.github.com/repos/${REPO}/contents/wachtrij`;
```

- Leest direct via Contents API (geen tussenstap nodig -- alleen files in `wachtrij/`).
- Toont per item: speeldatum, tijd, spelers, reserveringsdatum.
- Verversen herlaadt de Contents API.
- Verwijderen verwijdert het JSON-bestand via Contents API DELETE (geen workflow nodig).

### PAT-overlay

Verschijnt automatisch als `localStorage.knltb_pat` leeg is. PAT opgeslagen lokaal -- niet naar server gestuurd.

### Validatie

Velden krijgen rode rand bij leeg laten bij druk op "Baan reserveren". Hidden `<input>` per speler-slot wordt alleen ingevuld als dropdown-keuze gemaakt is.

### XSS-bescherming

Alle gerenderde user-data gaat door `escapeHtml()` (in beide wachtrij- en reserveringen-render). Voorkomt HTML-injection als een spelernaam ooit speciale tekens bevat.

---

## 6. Service Worker -- docs/sw.js

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

**Belangrijk:** na een wijziging aan `index.html` moet `CACHE` versie in `sw.js` omhoog, anders zien gebruikers de oude versie.

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

**Stappen:** checkout -> setup-python 3.11 -> `apt-get install xvfb` + pip install (undetected-chromedriver, selenium, google-api-python-client, google-auth) -> `Xvfb :99` + `python boek_baan.py ...` -> bij fout: upload `*.png` als artifact (3 dagen retentie).

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

**Input:** `cancel_id` (optioneel -- formaat `YYYY-MM-DD_HHMM_baan-slug`).

```yaml
permissions:
  contents: write
env:
  TZ: Europe/Amsterdam
```

Run: `python lees_reserveringen.py` (of met `--cancel ID`). Schrijft `reserveringen.json` en commit.

### 7.4 haal_leden_op.yml

**Trigger:** `workflow_dispatch` of `schedule: '0 5 * * 1'` (07:00 NL maandag, zomertijd).

**Permissions:** `contents: write` + `actions: write` voor `leden.json` push en het triggeren van de volgende workflow.

**Na succes:** triggert automatisch `haal_padel_sterktes.yml` via `gh workflow run`.

### 7.5 haal_padel_sterktes.yml

**Trigger:** `workflow_dispatch` (handmatig of automatisch na `haal_leden_op.yml`).

**Input:** `max_leden` (optioneel -- 0 = alle leden, >0 = testrun met N leden).

**Secrets:** `KNLTB_LOGINNAAM` + `KNLTB_WACHTWOORD` (mijnknltb.toernooi.nl, los van ETV Volley-credentials).

**Wat het doet:** logt in op mijnknltb.toernooi.nl, zoekt per lid via DoSearch het spelersprofiel, extraheert de Padel Dubbel speelsterkte + rating en schrijft die naar `leden.json`.

---

## 8. boek_baan.py -- stap voor stap

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

1. **Login** -- Cloudflare-wait, cookie-banner, JS-property setter voor bondsnummer + wachtwoord (triggert React/Vue input/change events), submit
2. **Klik "Baan afhangen"** op de Reserveringen-pagina
3. **Voeg 3 spelers toe** -- zie volgende sectie
4. **Wacht tot 07:01 NL** als nodig (zie boekvenster-timing op 07:01 NL)
5. **Kies dag + dagdeel** -- retry-loop met back-redirect recovery (max 3 pogingen)
6. **Kies tijdslot** -- zoekt `.timeincourt` of `[data-hour]` cellen in de padel-rij via absolute Y-positie
7. **Bevestig** -- intercepteert jQuery.ajax POST naar `/Ajax/Profile/SaveReservation`
8. **Verifieer** -- bezoek `/mijn/Reservations` en `/me/Reservations`, check op datum + tijd in body
9. **Google Agenda-event** -- Service Account API call, kleur groen, popup-herinnering 60 min

### Strikte spelers-matching

Een element wordt **alleen** geklikt als zijn genormaliseerde innerText EXACT gelijk is aan:
- Volledige naam (bv. "Chris van Waardenburg")
- OF voornaam + achternaam zonder tussenvoegsel (bv. "Chris Waardenburg")

**Achternaam-alleen wordt NOOIT geaccepteerd als match-tekst.** De achternaam wordt wel gebruikt als laatste zoekterm-fallback, maar het te klikken element moet alsnog exact "Chris van Waardenburg" zijn.

**Selectors (in volgorde):**
1. `//*[@role='option']`
2. `//li[contains(., 'achternaam')]`
3. `//div[contains(@class, 'player|suggestion|result|item')]`

**Geen brede `//*` fallback** -- die matchte het "Recent mee gespeeld" paneel en koppelde een verkeerde click-handler.

**Post-klik verificatie:** na elke speler-click moet de doelnaam zichtbaar zijn op de pagina in een non-input element. Zo niet -> `return False`, hele reservering faalt.

### kies_dag retry-loop

3 pogingen met automatisch herstel:
- Voor elke poging: detecteer huidige URL. Als op `ReservationsPlayers` (back-redirect van eerdere poging): klik Volgende om weer naar dag-pagina.
- Re-fetch daypart-element + Volgende-knop in elke poging (geen stale references).
- Klik daypart via ActionChains (isTrusted=true) -- synthetische events worden door ETV's jQuery genegeerd.
- Na submit: 4 mogelijke outcomes:
  1. URL = `ReservationsCourt` -> success
  2. Body bevat `:00` of `:30` -> AJAX-wizard success
  3. URL = `ReservationsPlayers` -> server weigerde dagdeel -> retry
  4. Onbekend -> retry

### Boekvenster-timing op 07:01 NL

```python
# Vlak voor kies_dag:
doel = reserveringsdatum.replace(hour=7, minute=1, second=0)
if nu.date() == reserveringsdatum.date() and nu < doel:
    time.sleep(int((doel - nu).total_seconds()))

kies_dag(driver, ...)
kies_baan_en_tijd(driver, ...)
bevestig(driver)
```

cron-job.org triggert om **06:50 NL**. Login + spelers (~3-4 min) loopt tijdens de wachttijd voor 07:00 -- die stappen hebben geen slot-validatie. **Vanaf 07:01 NL** (1 min buffer voor klok-skew) doet het script kies_dag -> kies_baan_en_tijd -> bevestig in een doorloop. Bevestig valt rond 07:02-03.

**Waarom de wait voor kies_dag, niet voor bevestig?** Run #63 bewees dat ETV's server de daypart-selectie zelf weigert voor 07:00. Zie sectie 12.8.

### bevestig + BEZET-retry (race-conditie tussen kies en bevestig)

`bevestig()` retourneert een 3-state string:

| Return | Betekenis |
|---|---|
| `'OK'`    | Reservering geslaagd |
| `'BEZET'` | Server wees af met race-loss-patroon -> main() doet retry met andere baan |
| `'FOUT'`  | Andere fout -> script stopt (geen retry zinvol) |

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

### Diagnose-logging

Na elke wizard-stap dumpt het script welke spelers zichtbaar zijn op de huidige pagina:

```
SPELERS-CHECK [na voeg_spelers_toe (4 verwacht)] URL=.../ReservationsDay
   Aanwezig (4/4): [...]
```

---

## 9. lees_reserveringen.py -- reserveringen + annuleren

### Werking

Zonder argumenten: scrape `/mijn/Reservations`, schrijf `reserveringen.json`, commit/push.

Met `--cancel <id>`: annuleer die reservering (klik Annuleren-knop in rij met matching datum+tijd), bevestig dialoog, dan opnieuw scrape. Plus: verwijder matching Google Agenda-event (zoekt 'Padel'-events in window -1u tot +2u rond het slot, matcht op start-datetime + 'Padel' in summary).

### ID-format

`YYYY-MM-DD_HHMM_baan-slug`, bijv. `2026-05-31_1500_padel-1`. Wordt deterministisch gebouwd in `maak_id()` zodat PWA en script dezelfde ID gebruiken.

### Scrape-heuristieken

Drie strategieen:
1. **Tabel-rijen** -- alle `<tr>` met >=2 `<td>` cellen
2. **Class-based divs** -- `[class*="booking|reservation|reservering"]`
3. **Cancel-buttons** -- `<button|a|[role=button]>` met tekst/class/title/aria-label bevattend `annuleer|cancel|verwijder|delete`

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
      "cancel": { "btnTekst": "Annuleren" }
    }
  ]
}
```

---

## 10. haal_leden_op.py -- ledenlijst scrapen

1. Login via Selenium/UC (zelfde patroon als boek_baan.py)
2. Klik "Ledenlijst"-tab
3. Scrape namen uit eerste tabelkolom: `name.length > 3 && name.indexOf(' ') >= 0`
4. **Paginering** -- klik paginanummer N+1, fallback `>>` / "Volgende"
5. **Fallback per letter** -- als <10 namen na alle pagina's: door alfabet en filter op een letter
6. Sorteer + schrijf `leden.json` + commit/push met retry-loop

Cron `'0 5 * * 1'` = maandag 07:00 NL (zomertijd). Na succesvolle run triggert de workflow automatisch `haal_padel_sterktes.yml`.

---

## 11. haal_padel_sterktes.py -- padel speelsterktes ophalen

### Doel

Vult de velden `sterkte_padel` en `rating_padel` in `leden.json` voor elk lid dat een Padel Dubbel speelsterkte heeft op mijnknltb.toernooi.nl.

### Strategie

Geen Selenium -- mijnknltb.toernooi.nl heeft geen Cloudflare-bescherming. Pure `requests.Session` volstaat.

```
1. Accepteer cookie wall (/cookiewall)
2. Login via CSRF-token + formulierveld 'Login' + 'Password'
3. Per lid: GET /find/player/DoSearch?Query={bondsnummer}
            -> player-profile link uit HTML
4. GET /player-profile/{guid}
            -> Padel Dubbel sterkte + rating uit server-rendered HTML
5. Schrijf terug naar leden.json
```

### Login-flow (mijnknltb)

mijnknltb.toernooi.nl gebruikt ASP.NET MVC met CSRF-tokens:

1. **Cookie wall:** GET `/cookiewall?returnurl=/user/login` -> POST acceptatie met `__RequestVerificationToken` + `AcceptAll=true`
2. **Login-pagina:** GET `/user/login` -> extraheer `__RequestVerificationToken` (len ~92)
3. **Login-POST:** veld heet `Login` (niet `Username`!), plus `Password`, `__RequestVerificationToken`, `ReturnUrl`
4. **Verificatie:** na POST mag de URL niet meer `/login` of `/cookiewall` bevatten

Credentials: `KNLTB_LOGINNAAM` + `KNLTB_WACHTWOORD` (los van ETV Volley-credentials).

### DoSearch endpoint

```
GET /find/player/DoSearch?Query={bondsnummer}&Page=1&SportID=0
Headers:
  X-Requested-With: XMLHttpRequest
  Referer: https://mijnknltb.toernooi.nl/find/player
  Accept: text/html, */*; q=0.01
```

Retourneert HTML met `href="/player-profile/{guid}"` links. Eerste match wordt gebruikt.

### Padel sterkte extractie

HTML-patroon op de profielpagina:

```html
<span title="Padel Dubbel">
  <span class="tag-duo__title">7</span>   <!-- sterkte (integer) -->
  <span class="tag-duo__value">7,3215</span>  <!-- rating (decimaal) -->
</span>
```

Regex (DOTALL):
```python
r'title="Padel Dubbel"[^>]*>.*?'
r'<span class="tag-duo__title">(.*?)</span>.*?'
r'<span class="tag-duo__value">(.*?)</span>'
```

### Sessie-beheer

- Elke 100 leden: check of sessie nog geldig is via GET `/user`
- Bij redirect naar login: automatisch herlogin
- DoSearch of profielpagina redirect naar login: herlogin + opnieuw proberen

### Output in leden.json

Elk lid-object krijgt twee extra velden:
```json
{
  "naam": "Toine Aanraad",
  "bondsnummer": "12345678",
  "sterkte_padel": "7",
  "rating_padel": "7,3215"
}
```
Leeg string als geen Padel Dubbel rating gevonden.

---

## 12. Technische valkuilen en beslissingen

### 12.1 Cloudflare-omzeiling (ETV Volley)

`undetected-chromedriver` past de Chrome binary aan zodat Cloudflare-detectie (`navigator.webdriver`) faalt. **Geen `--headless`**: headless-modus laat signatures achter die Cloudflare herkent. Xvfb simuleert een echt scherm.

### 12.2 isTrusted=true noodzakelijk

ETV's jQuery-handlers filteren synthetische events (`isTrusted=false`) weg. Dat geldt voor:
- **Spelers-suggesties** -- ActionChains.move_to_element + click is nodig
- **Daypart-elementen** -- idem
- **Tijdslot-cellen** -- idem

`dispatchEvent` / `el.click()` via JS hebben `isTrusted=false` en worden genegeerd.

### 12.3 GitHub Actions cron is onbetrouwbaar

Documented limitation: scheduled workflows kunnen volledig overgeslagen worden bij hoge load. Bewezen: de eerste productie-nacht (29-05 06:55 NL) vuurde de cron simpelweg niet.

**Oplossing:** externe scheduler ([cron-job.org](https://cron-job.org)) die via de GitHub API een `workflow_dispatch` event verstuurt.

### 12.4 Recent mee gespeeld race condition

De `_voeg_speler_toe()` had ooit een brede XPath-fallback die ook elementen in het "Recent mee gespeeld" paneel matchte -- voor spelers die je recent had gereserveerd stond hun naam al zichtbaar voor de typeahead uberhaupt loaded. Resultaat: verkeerde click-handler, speler nooit server-side geregistreerd.

**Fix:** brede fallback verwijderd. Alleen `role=option`, `<li>` en `<div class=player/suggestion/result/item>`.

### 12.5 Foute speler-selectie bug (Christel-incident)

Op 28-05 selecteerde het oude script per ongeluk "Christel Beckmann Asselman" ipv "Chris van Waardenburg". Oorzaak: de XPath `contains(., 'Waardenburg')` matchte een container-element met meerdere namen.

**Fix:** strikte text-equality. De tekst van het te klikken element MOET genormaliseerd exact gelijk zijn aan een geaccepteerde naamvorm.

### 12.6 Push-race-conditions

Vier bronnen pushen naar main: jij, GitHub Actions bot (wachtrij), verwerk_wachtrij workflow, lees_reserveringen.py.

**Fix:** alle push-plekken hebben een retry-loop:
```bash
for i in 1 2 3 4 5; do
  git pull --rebase origin main || true
  if git push; then exit 0; fi
  sleep $i
done
```

### 12.7 Cron-vroege start vs boekvenster-timing

Cron triggert om 06:50, prep duurt 5 min, dan sleep tot 07:01 vlak voor `kies_dag` -- prep loopt dus tijdens de wachttijd.

### 12.8 Boekvenster geldt vanaf dag-keuze, niet alleen bevestig

Run #63 bewees dat ETV's server al de **daypart-selectie zelf** weigert voor 07:00. Het hele blok kies_dag -> kies_baan_en_tijd -> bevestig moet na de slot-opening lopen.

**Fix:** sleep verschoven naar vlak voor `kies_dag`. Vanaf 07:01 NL doet het script de hele wizard in een doorloop.

### 12.9 ETV "1 actieve reservering"-rule (vermoeden)

ETV lijkt impliciet geen 2e actieve reservering toe te staan per lid. Niet 100% gevalideerd.

### 12.10 Spelers selecteren via UUID (data-id)

De juiste manier om een speler te selecteren is via het `data-id` attribuut van het `.addPlayer`-element. Na succesvolle add moet de data-id zichtbaar zijn in `#youPlayWith`.

**Waarom data-id verificatie:** visible name kan misleiden (HTML toonde dubbele spaties), maar UUIDs liegen niet.

### 12.11 Race-conditie: andere boeker pakt de baan

Vlak na 07:00 NL hangen meerdere clubleden tegelijk op de portal. Het venster tussen kies en bevestig is ~1-2 sec.

**Detectie-patronen** (case-insensitive substring-match op AJAX-response):
- `"niet gevonden"`, `"not found"`, `"al gereserveerd"`, `"reeds geboekt"`, `"niet meer beschikbaar"`

`bevestig()` retourneert `'BEZET'` -> main() navigeert terug, doet `driver.refresh()` voor verse DOM, en probeert volgende baan. De DOM IS de filter -- bezette tijdcellen zijn er simpelweg niet meer.

### 12.12 Typeahead substring-matches voegen mystery-spelers toe (Daniel-bug)

Run #68 + #69 faalden op het toevoegen van Johan Janssen. Oorzaak: zoekterm "Daniel Enderink" triggerde typeahead met meerdere cards; een hover-event tijdens ActionChains voegde ook "Ellen Daniels" toe.

**Fix:** defensieve scan-en-verwijder. Na elke succesvolle speler-add scant `_ruim_onverwachte_spelers_op()` `#youPlayWith` op data-ids; alles buiten de verwachte set wordt verwijderd via klik op `a.removePlayer[data-id="..."]`.

### 12.13 mijnKNLTB login -- formulierveld heet 'Login', niet 'Username'

mijnknltb.toernooi.nl gebruikt een ASP.NET Identity form met veldnaam `Login` (niet `Username` zoals standaard is bij veel andere sites). Bovendien vereist de site eerst acceptatie van een cookie wall voordat de loginpagina bereikbaar is. Credentials zijn los van ETV Volley -- `KNLTB_LOGINNAAM` + `KNLTB_WACHTWOORD`.

### 12.14 YAML encoding-corruptie door PowerShell Set-Content

PowerShell's `Set-Content -Encoding utf8` schrijft een UTF-8 BOM (byte 0xEF 0xBB 0xBF) aan het begin van het bestand. GitHub Actions YAML-parser herkent dan de `workflow_dispatch` trigger niet meer. Bovendien corrupteert het emoji- en speciale tekens in shell `run:` blokken.

**Fix:** schrijf YAML-bestanden altijd met de `Write`-tool (Claude Code) of met PowerShell via `[System.IO.File]::WriteAllText(path, content, [System.Text.UTF8Encoding]::new($false))`. Gebruik geen emoji in YAML-bestanden.

---

## 13. Wijzigingen aanbrengen

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
```

### Cron-tijd wijzigen

In cron-job.org -> cronjob -> tab Schedule. **Niet** in `verwerk_wachtrij.yml` editen (die schedule is een fallback).

### Nieuwe versie van de PWA uitrollen

1. Wijzig `docs/index.html`
2. Bump `CACHE` in `docs/sw.js`:
   ```javascript
   const CACHE = 'padel-v17';   // was v16
   ```
3. Commit + push. GitHub Pages serveert binnen 1-3 min.

### Cron-job.org PAT vernieuwen

Bij PAT-expiry: nieuwe classic PAT met `workflow` scope -> cron-job.org -> Headers -> `Authorization` waarde aanpassen -> Save -> Test run.

### Site-redesign van ETV Volley

Bij grote HTML-veranderingen kunnen stappen falen. Diagnose via screenshots (artifacts bij failed run):

| Screenshot | Moment |
|------------|--------|
| `01_login_pagina.png` | Loginpagina geladen |
| `02_na_login.png` | Direct na inloggen |
| `02b_login_mislukt.png` | Alleen als wachtwoordveld nog zichtbaar |
| `03_reserveer_pagina.png` | Reserveringen-overzicht |
| `04_na_afhangen_klik.png` | Na klikken "Baan afhangen" |
| `05_spelers_pagina.png` | Spelers-pagina geladen |
| `05b_zoek_*` | Tijdens zoeken speler 2/3/4 |
| `06_spelers_toegevoegd.png` | Na toevoegen alle spelers |
| `07_dag_pagina.png` | Dag-keuze pagina |
| `08_dag_geselecteerd_poging{N}.png` | Per kies_dag-poging |
| `09_baan_pagina.png` | Baan/tijdslot-pagina |
| `10_baan_geselecteerd.png` | Na tijdslot-klik |
| `11_bevestig_pagina.png` | Confirm-pagina |
| `12_na_bevestiging.png` | Na bevestig-klik |

---

## 14. Toekomstige features -- multi-user setup

**Status: niet geimplementeerd. Geplande feature voor wanneer meerdere ETV-leden de tool willen gebruiken.**

Op dit moment is alle code gericht op een account (Joris's credentials in `secrets.ETVVOLLEY_BONDSNUMMER` + `SPELER1 = "Joris van den Broek"` hardcoded). Onderstaand plan maakt dezelfde repo bruikbaar voor meerdere ETV-leden zonder fork.

### 14.1 Architectuur

Per-user GitHub Secrets in dezelfde repo:

| Secret | Voor |
|---|---|
| `ETVVOLLEY_BONDSNUMMER_JORIS` / `ETVVOLLEY_WACHTWOORD_JORIS` | Joris's ETV-login |
| `ETVVOLLEY_BONDSNUMMER_TOINE` / `ETVVOLLEY_WACHTWOORD_TOINE` | Toine's ETV-login |
| `GOOGLE_CALENDAR_CREDENTIALS` | shared service-account JSON (een voor alle users) |
| `GOOGLE_CALENDAR_ID_JORIS` | Joris's agenda-ID |
| `GOOGLE_CALENDAR_ID_TOINE` | Toine's agenda-ID (optioneel) |

### 14.2 Workflow-wijzigingen

`boek.yml`, `beheer_reserveringen.yml`, `verwerk_wachtrij.yml` krijgen een `gebruiker` input + conditional env-vars:

```yaml
env:
  ETVVOLLEY_BONDSNUMMER: ${{ inputs.gebruiker == 'toine' && secrets.ETVVOLLEY_BONDSNUMMER_TOINE || secrets.ETVVOLLEY_BONDSNUMMER_JORIS }}
  ETVVOLLEY_WACHTWOORD:  ${{ inputs.gebruiker == 'toine' && secrets.ETVVOLLEY_WACHTWOORD_TOINE  || secrets.ETVVOLLEY_WACHTWOORD_JORIS }}
  SPELER1_NAAM:          ${{ inputs.gebruiker == 'toine' && 'Toine Aanraad' || 'Joris van den Broek' }}
```

### 14.3 Python-scripts

Een regel verandert:

```python
SPELER1 = os.environ.get("SPELER1_NAAM", "Joris van den Broek")
```

### 14.4 Data-isolatie

| Was | Wordt |
|---|---|
| `reserveringen.json` | `reserveringen_joris.json` + `reserveringen_toine.json` |
| `wachtrij/<datum>_<tijd>.json` | `wachtrij/joris/<datum>_<tijd>.json` + `wachtrij/toine/<datum>_<tijd>.json` |
| `leden.json` | Blijft gedeeld (een ledenlijst voor de hele club) |

### 14.5 PWA-aanpassingen

- **Gebruiker-selector** (dropdown) bovenaan of in tandwiel
- `localStorage.knltb_gebruiker` opslaan
- `RESERV_URL` dynamisch: `reserveringen_${gebruiker}.json`
- `WACHTRIJ_API` dynamisch: `contents/wachtrij/${gebruiker}`
- `workflow_dispatch` body: voeg `inputs.gebruiker` toe

### 14.6 Google Calendar setup voor extra gebruiker

Het bestaande service-account kan voor meerdere agendas tegelijk schrijven. Nieuwe gebruiker doet zelf:

1. Google Agenda -> naast eigen agenda -> **Instellingen en delen**
2. Onder "Personen met toegang" -> **Personen uitnodigen**
3. Plak het service-account email (vind je in de JSON onder `"client_email"`)
4. Rol: **"Afspraken beheren"**
5. Geef de eigen calendar-ID door aan repo-eigenaar

### 14.7 Effort-inschatting

| Onderdeel | Tijd |
|---|---|
| 3 workflow-files (boek/beheer/verwerk_wachtrij) -- input + conditional env | 15 min |
| `boek_baan.py` + `lees_reserveringen.py` parametrize | 15 min |
| `verwerk_wachtrij.yml` per-user loop | 10 min |
| File-rename `reserveringen.json` + wachtrij-folder restructure | 10 min |
| PWA gebruiker-selector + dynamic URLs | 15 min |
| Docs (README + knltb-autoboek.md) | 10 min |
| Per nieuwe gebruiker: ETV-secrets + Google Calendar-deling | ~5 min |
| **Totaal eenmalige refactor** | **~1.5 uur** |

---

## 15. Operationele veiligheidsnetten

### 15.1 Concurrency-groepen

Alle 3 workflows (`boek.yml`, `beheer_reserveringen.yml`, `verwerk_wachtrij.yml`) hebben:

```yaml
concurrency:
  group: knltb-account-joris
  cancel-in-progress: false
```

**Waarom:** twee gelijktijdige Selenium-sessies tegen een ETV-account veroorzaken race-condities. `cancel-in-progress: false` zorgt dat een lopende boeking nooit halverwege wordt afgekapt.

Bij toekomstige multi-user wordt `group: knltb-account-${inputs.gebruiker}`.

### 15.2 Auto-issue bij failure

Elke workflow heeft een `if: failure()` step die via `gh issue create` een GitHub Issue opent met run-link, context en label `auto-failure,<bron>`.

### 15.3 Healthchecks.io dead-man's-switch (optioneel)

Als secret `HEALTHCHECK_PING_URL` is gezet, pingt `verwerk_wachtrij.yml`:
- `/start` bij begin van elke run
- success URL als alle stappen ok zijn
- `/fail` als iets faalt

Setup (~3 min): account op [healthchecks.io](https://healthchecks.io) -> Add Check -> period 26 hours -> kopieer ping URL als Secret.

**Voordeel:** ook bij compleet stille failures (PAT verlopen, cron-job.org account opgezegd, GitHub Actions outage) krijg je binnen 24u een alert.

### 15.4 Wachtrij-TTL

`verwerk_wachtrij.yml` verwijdert items ouder dan **60 dagen** zonder boeking-trigger. Voorkomt dat een vergeten plan van maanden terug spontaan een boeking creert.

### 15.5 Dry-run modus

`boek_baan.py --dry-run`: loopt door alle stappen maar slaat de daadwerkelijke bevestig-klik over. Geen state-pollution.

Via PWA: amber toggle boven de Reserveer-knop. State persisteert NIET in localStorage.

Workflow: `boek.yml` heeft input `dry_run` (default false) die wordt doorgegeven als `--dry-run` flag.

### 15.6 PAT-expiry waarschuwing (PWA)

PWA toont badge op tandwiel-icoon:
- amber bij 8-30 dagen tot verloop
- rood bij 0-7 dagen
- pulsende donkerrood na verloop + harde error-toast

Setup: vul de verloopdatum in het PAT-sheet van de PWA. Bewaard in `localStorage` als `knltb_pat_verloopt`.

### 15.7 Spelers 2-poging retry

`voeg_spelers_toe()` doet per speler maximaal 2 pogingen. Bij fail: `driver.refresh()` + retry. De defensieve cleanup zorgt dat eerder-toegevoegde spelers de refresh overleven.

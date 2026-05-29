# knltb-autoboek — Volledige documentatie

**GitHub-repository:** `joris-vandenBroek/knltb-autoboek`  
**Doel:** Automatisch een padelbaan reserveren bij ETV Volley via de KNLTB-ledenportal, aangestuurd via een PWA op de telefoon, inclusief Google Agenda-integratie en wachtrij voor toekomstige boekingen.

---

## Inhoudsopgave

1. [Hoe werkt het in grote lijnen](#1-hoe-werkt-het-in-grote-lijnen)
2. [Repository-structuur](#2-repository-structuur)
3. [Benodigde GitHub Secrets](#3-benodigde-github-secrets)
4. [Externe cron-trigger via cron-job.org](#4-externe-cron-trigger-via-cron-joborg)
5. [PWA-frontend — docs/index.html](#5-pwa-frontend--docsindexhtml)
6. [Service Worker — docs/sw.js](#6-service-worker--docsswjs)
7. [Workflows](#7-workflows)
8. [boek_baan.py — stap voor stap](#8-boek_baanpy--stap-voor-stap)
9. [lees_reserveringen.py — reserveringen + annuleren](#9-lees_reserveringenpy--reserveringen--annuleren)
10. [haal_leden_op.py — ledenlijst scrapen](#10-haal_leden_oppy--ledenlijst-scrapen)
11. [Technische valkuilen en beslissingen](#11-technische-valkuilen-en-beslissingen)
12. [Wijzigingen aanbrengen](#12-wijzigingen-aanbrengen)

---

## 1. Hoe werkt het in grote lijnen

```
Gebruiker (telefoon)
        │  tikt op "Baan boeken" in de PWA
        ▼
docs/index.html (GitHub Pages PWA)
        │  POST naar GitHub Actions API (met PAT-token)
        ▼
.github/workflows/boek.yml
        │  Start Python-script met datum/tijd/spelers
        ▼
boek_baan.py
        │  IF speeldatum > dag+2:
        │     → schrijf wachtrij/<datum>_<tijd>.json + commit/push
        │  ELSE:
        │     → login + spelers + dag + baan + (wacht tot 07:01 NL) + bevestig
        ▼
Google Agenda  (via Service Account, optioneel)
        ▼
Klaar — e-mail van ETV Volley + agenda-event

╔══════════════════════════════════════════════════════════╗
║ Voor wachtrij-items (dag+3 en verder):                   ║
║                                                          ║
║ cron-job.org (06:50 NL dagelijks)                        ║
║     │  POST naar GitHub Actions API                      ║
║     ▼                                                    ║
║ verwerk_wachtrij.yml                                     ║
║     │  Voor elk wachtrij-bestand met                     ║
║     │  boekingsdatum == vandaag:                         ║
║     │     → triggert boek.yml met die inputs             ║
║     ▼                                                    ║
║ boek.yml → boek_baan.py → bevestig om 07:01 NL ✓         ║
╚══════════════════════════════════════════════════════════╝
```

De **ledenlijst** (`leden.json`) wordt los bijgehouden via `haal_leden_op.yml` (wekelijks of handmatig). Gebruikt door de PWA voor de speler-dropdowns.

De **actieve reserveringen** (`reserveringen.json`) worden bijgehouden via `lees_reserveringen.py` + `beheer_reserveringen.yml`, getriggerd vanuit de PWA bij Verversen of Annuleren.

---

## 2. Repository-structuur

```
knltb-autoboek/
├── boek_baan.py                 # Hoofdscript: Selenium-boeking + wachtrij
├── lees_reserveringen.py        # Scrape + annuleer actieve reserveringen
├── haal_leden_op.py             # Scrape de ledenlijst → leden.json
├── leden.json                   # Cache van alle ETV-leden (~970 namen)
├── reserveringen.json           # Cache van actieve reserveringen
├── wachtrij/                    # Boekingen voor speeldatums > dag+2
│   ├── .gitkeep
│   └── YYYY-MM-DD_HHMM.json     # Per ingeplande boeking
├── docs/                        # PWA (GitHub Pages source)
│   ├── index.html               # Single-page app
│   ├── sw.js                    # Service Worker (cache versioning)
│   ├── manifest.json            # PWA-manifest
│   ├── logo.png + icon-192/512.png
└── .github/workflows/
    ├── boek.yml                 # Voer een boeking uit
    ├── verwerk_wachtrij.yml     # Verwerk wachtrij (door cron-job.org getriggerd)
    ├── beheer_reserveringen.yml # Scrape of annuleer reservering (vanuit PWA)
    └── haal_leden_op.yml        # Ledenlijst-refresh (maandag 07:00)
```

GitHub Pages is ingesteld op de `docs/`-map van de `main`-branch. De PWA is bereikbaar via `https://joris-vandenbroek.github.io/knltb-autoboek/`.

---

## 3. Benodigde GitHub Secrets

In te stellen via **GitHub → Repository → Settings → Secrets and variables → Actions**:

| Secret | Inhoud |
|--------|--------|
| `KNLTB_BONDSNUMMER` | Bondsnummer / gebruikersnaam voor etv-volley.nl |
| `KNLTB_WACHTWOORD` | Wachtwoord voor etv-volley.nl |
| `GOOGLE_CALENDAR_CREDENTIALS` | Volledige JSON-inhoud van het Service Account-sleutelbestand |
| `GOOGLE_CALENDAR_ID` | Agenda-ID (bijv. `primary` of e-mailadres) |

Het **GitHub Personal Access Token (PAT)** wordt *niet* als Secret opgeslagen, maar:
- **In de PWA** in `localStorage` (sleutel `knltb_pat`) voor PWA-triggers (workflow_dispatch)
- **In cron-job.org** in een header voor de dagelijkse wachtrij-trigger

Beide PATs hebben minimaal `workflow` scope nodig (classic) of `Actions: Read and write` op deze repo (fine-grained).

---

## 4. Externe cron-trigger via cron-job.org

**Waarom extern?** GitHub Actions' eigen `schedule:`-triggers zijn best-effort en kunnen volledig overgeslagen worden, vooral bij nieuwe workflows of tijdens hoge load. Dit gebeurde inderdaad op de eerste productie-nacht: de cron `'55 4 * * *'` in `verwerk_wachtrij.yml` vuurde simpelweg niet, ook al was de workflow `active`. cron-job.org is een externe service die wél deterministisch op tijd vuurt.

### Setup

1. **Classic PAT aanmaken** op [github.com/settings/tokens/new](https://github.com/settings/tokens/new):
   - Scope: alleen `workflow` (geeft automatisch `repo`-rechten)
   - Expiration: bv. 1 jaar
2. **Account** op [cron-job.org](https://cron-job.org) → Create cronjob:
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
3. **Test run** → moet 204 No Content geven

### Trade-offs

- ✅ Betrouwbaar (vuurt op tijd)
- ✅ Heeft notificaties bij failure
- ⚠️ Externe service heeft je PAT
- ⚠️ Cron-job.org gratis tier heeft een limiet (~1 trigger/min, ruim voldoende voor dagelijks)

---

## 5. PWA-frontend — docs/index.html

Eén HTML-bestand zonder frameworks. Werkt als installeerbare PWA op iPhone en Android. Sectie-volgorde:

1. **Header** met ETV Volley-logo + ⚙️-knop voor PAT
2. **Wanneer** — datumkiezer + tijdkeuze (08:00–21:30, stappen van 30 min, standaard 15:00)
3. **Medespelers** — 3 dropdowns met zoekfilter (PrimeFaces-stijl)
4. **📅 Mijn boekingen** — actieve reserveringen + 🗑️ annuleren per item
5. **🕒 Ingeplande reserveringen** — wachtrij + 🗑️ verwijderen per item
6. **🎾 Baan boeken** — vast onderaan, triggert workflow

### Mobile sizing

Basis font-size `22px` (op viewport < 380px: `20px`). Velden minimaal 58px hoog, knoppen 76px. Doel: comfortabel tappen op midrange telefoons (S10+, iPhone 12, etc.).

### Date-picker click-fix

De native `<input type="date">` ligt als transparante overlay op de visuele knop. CSS-regel `pointer-events: none` op `.date-native` zorgt dat het hele veld klikbaar is (niet alleen het smalle kalender-icoon-gebied dat sommige browsers default geven). De JS-handler op `.date-picker-btn` roept `showPicker()` aan.

### Mijn boekingen (PWA-card)

```javascript
const RESERV_URL = `https://raw.githubusercontent.com/${REPO}/main/reserveringen.json`;
```

- **Laden op page open:** fetch `reserveringen.json` van GitHub raw, render lijst.
- **🔄 Verversen:** workflow_dispatch op `beheer_reserveringen.yml` met `cancel_id=""` → script logt in, scrape, commit/push update naar `reserveringen.json`. PWA pollt 4× tussen 90s en 180s om nieuwe state te tonen.
- **🗑️ Annuleer-knop per item:** confirm-dialoog → workflow_dispatch met `cancel_id="YYYY-MM-DD_HHMM_baan-slug"` → script annuleert op ETV-site + verwijdert agenda-event + ververst lijst.

### Ingeplande reserveringen (wachtrij, PWA-card)

```javascript
const WACHTRIJ_API = `https://api.github.com/repos/${REPO}/contents/wachtrij`;
```

- Leest direct via Contents API (geen tussenstap nodig — alleen files in `wachtrij/`).
- Toont per item: speeldatum, tijd, spelers, boekingsdatum.
- 🔄 Verversen herlaadt de Contents API.
- 🗑️ verwijdert het JSON-bestand via Contents API DELETE (geen workflow nodig).

### PAT-overlay

Verschijnt automatisch als `localStorage.knltb_pat` leeg is. PAT opgeslagen lokaal — niet naar server gestuurd.

### Validatie

Velden krijgen rode rand bij leeg laten bij druk op "Baan boeken". Hidden `<input>` per speler-slot wordt alleen ingevuld als dropdown-keuze gemaakt is.

### XSS-bescherming

Alle gerenderde user-data gaat door `escapeHtml()` (in beide wachtrij- en reserveringen-render). Voorkomt HTML-injection als een spelernaam ooit speciale tekens bevat.

---

## 6. Service Worker — docs/sw.js

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

**Stappen:** checkout → setup-python 3.11 → `apt-get install xvfb` + pip install (undetected-chromedriver, selenium, google-api-python-client, google-auth) → `Xvfb :99` + `python boek_baan.py ...` → bij fout: upload `*.png` als artifact (3 dagen retentie).

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
2. Per bestand: bereken `boekingsdatum = speeldatum - 2 dagen`
3. Als `boekingsdatum == today` (NL-tijd):
   - `gh workflow run boek.yml --field datum=... --field tijd=... --field speler2=... etc.`
   - Verwijder het wachtrij-bestand
4. Commit + push de verwijderingen (retry-loop met rebase)

### 7.3 beheer_reserveringen.yml

**Trigger:** alleen `workflow_dispatch`.

**Input:** `cancel_id` (optioneel — formaat `YYYY-MM-DD_HHMM_baan-slug`).

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

## 8. boek_baan.py — stap voor stap

### Constanten

```python
LOGIN_URL     = "https://www.etv-volley.nl/mijn"
RESERVEER_URL = "https://www.etv-volley.nl/mijn/Reservations"
SPELER1       = "Joris van den Broek"   # altijd speler 1
PADEL_BANEN   = ["Padel 1", ..., "Padel 6"]
```

### Wachtrij-pad

```python
boekingsdatum = speeldatum - timedelta(days=2)

if nu.date() < boekingsdatum.date():
    _zet_in_wachtrij(args.datum, args.tijd, args.speler2, args.speler3, args.speler4)
    sys.exit(0)
```

`_zet_in_wachtrij()`:
1. Schrijf `wachtrij/<datum>_<tijdslug>.json` met `datum`, `tijd`, `spelers` (4 namen), `ingediend` timestamp
2. `git add` + `git commit` + push met retry-loop (max 5 pogingen, `git pull --rebase` tussen elke poging)

### Direct-boek-pad

1. **Login** — Cloudflare-wait, cookie-banner, JS-property setter voor bondsnummer + wachtwoord (triggert React/Vue input/change events), submit
2. **Klik "Baan afhangen"** op de Reserveringen-pagina
3. **Voeg 3 spelers toe** — zie volgende sectie
4. **Kies dag + dagdeel** — retry-loop met back-redirect recovery (max 3 pogingen)
5. **Kies tijdslot** — zoekt `.timeincourt` of `[data-hour]` cellen in de padel-rij via absolute Y-positie
6. **Wacht tot 07:01 NL** als nodig (zie [bevestig-timing](#bevestig-timing-op-0701-nl))
7. **Bevestig** — intercepteert jQuery.ajax POST naar `/Ajax/Profile/SaveReservation`
8. **Verifieer** — bezoek `/mijn/Reservations` en `/me/Reservations`, check op datum + tijd in body
9. **Google Agenda-event** — Service Account API call, kleur groen, popup-herinnering 60 min

### Strikte spelers-matching

Een element wordt **alleen** geklikt als zijn genormaliseerde innerText EXACT gelijk is aan:
- Volledige naam (bv. "Chris van Waardenburg")
- OF voornaam + achternaam zonder tussenvoegsel (bv. "Chris Waardenburg")

**Achternaam-alleen wordt NOOIT geaccepteerd als match-tekst.** De achternaam wordt wel gebruikt als laatste zoekterm-fallback (bv. typen "Waardenburg" om de typeahead te triggeren), maar het te klikken element moet alsnog exact "Chris van Waardenburg" zijn.

**Selectors (in volgorde):**
1. `//*[@role='option']`
2. `//li[contains(., 'achternaam')]`
3. `//div[contains(@class, 'player|suggestion|result|item')]`

**Géén brede `//*` fallback** — die matchte het "Recent mee gespeeld" paneel en koppelde een verkeerde click-handler. Zie [valkuilen](#114-recent-mee-gespeeld-race-condition).

**Post-klik verificatie:** na elke speler-click moet de doelnaam zichtbaar zijn op de pagina in een non-input element. Zo niet → `return False`, hele boeking faalt. Beter falen dan een verkeerde speler boeken.

### kies_dag retry-loop

3 pogingen met automatisch herstel:
- Vóór elke poging: detecteer huidige URL. Als op `ReservationsPlayers` (back-redirect van eerdere poging): klik Volgende om weer naar dag-pagina.
- Re-fetch daypart-element + Volgende-knop in elke poging (geen stale references).
- Klik daypart via ActionChains (isTrusted=true) — synthetische events worden door ETV's jQuery genegeerd.
- Na submit: 4 mogelijke outcomes:
  1. URL = `ReservationsCourt` → success
  2. Body bevat `:00` of `:30` → AJAX-wizard success
  3. URL = `ReservationsPlayers` → server weigerde dagdeel → retry
  4. Onbekend → retry

### Bevestig-timing op 07:01 NL

```python
# Vlak vóór bevestig:
doel = boekingsdatum.replace(hour=7, minute=1, second=0)
if nu.date() == boekingsdatum.date() and nu < doel:
    time.sleep(int((doel - nu).total_seconds()))

bevestig(driver)
```

Cron-job.org triggert om **06:50 NL**. De prep (login + spelers + dag + baan) duurt ~5-6 min — eindigt rond 06:56. Dan sleep ~5 min tot **07:01 NL**, dan bevestig-klik. 1 min buffer na slot-opening (07:00) compenseert server-klok-skew.

### Diagnose-logging

Na elke wizard-stap dumpt het script welke spelers zichtbaar zijn op de huidige pagina:

```
📊 SPELERS-CHECK [na voeg_spelers_toe (4 verwacht)] URL=.../ReservationsDay
   ✓ Aanwezig (4/4): [...]
```

Bij "MIST 3 van 4" weten we direct waar in de wizard de server-side state verloren is gegaan.

---

## 9. lees_reserveringen.py — reserveringen + annuleren

### Werking

Zonder argumenten: scrape `/mijn/Reservations`, schrijf `reserveringen.json`, commit/push.

Met `--cancel <id>`: annuleer die boeking (klik Annuleren-knop in rij met matching datum+tijd), bevestig dialoog, dan opnieuw scrape. Plus: verwijder matching Google Agenda-event (zoekt 'Padel'-events in window -1u tot +2u rond het slot, matcht op start-datetime + 'Padel' in summary).

### ID-format

`YYYY-MM-DD_HHMM_baan-slug`, bijv. `2026-05-31_1500_padel-1`. Wordt deterministisch gebouwd in `maak_id()` zodat PWA en script dezelfde ID gebruiken.

### Scrape-heuristieken

Drie strategieën:
1. **Tabel-rijen** — alle `<tr>` met ≥2 `<td>` cellen
2. **Class-based divs** — `[class*="booking|reservation|reservering|boeking"]`
3. **Cancel-buttons** — `<button|a|[role=button]>` met tekst/class/title/aria-label bevattend `annuleer|cancel|verwijder|delete|prullenbak`

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

## 10. haal_leden_op.py — ledenlijst scrapen

1. Login via Selenium/UC (zelfde patroon)
2. Klik "Ledenlijst"-tab
3. Scrape namen uit eerste tabelkolom: `name.length > 3 && name.indexOf(' ') >= 0`
4. **Paginering** — klik paginanummer N+1, fallback `»` / "Volgende" / `›`
5. **Fallback per letter** — als <10 namen na alle pagina's: door alfabet en filter op één letter
6. Sorteer + schrijf `leden.json` + commit/push met retry-loop

Cron `'0 5 * * 1'` = maandag 07:00 NL (zomertijd; in winter wordt het 06:00 — niet kritiek voor ledenlijst-refresh).

---

## 11. Technische valkuilen en beslissingen

### 11.1 Cloudflare-omzeiling

`undetected-chromedriver` past de Chrome binary aan zodat Cloudflare-detectie (`navigator.webdriver`) faalt. **Geen `--headless`**: headless-modus laat signatures achter die Cloudflare herkent. Xvfb simuleert een echt scherm.

### 11.2 isTrusted=true noodzakelijk

ETV's jQuery-handlers filteren synthetische events (`isTrusted=false`) weg. Dat geldt voor:
- **Spelers-suggesties** — ActionChains.move_to_element + click is nodig
- **Daypart-elementen** — idem
- **Tijdslot-cellen** — idem

`dispatchEvent` / `el.click()` via JS hebben `isTrusted=false` en worden genegeerd. UI lijkt te updaten maar server-side komt het niet door.

### 11.3 GitHub Actions cron is onbetrouwbaar

Documented limitation: scheduled workflows kunnen volledig overgeslagen worden bij hoge load, en hebben vooral kort na toevoeging vertraging (uren tot dagen). Bewezen: de eerste productie-nacht (29-05 06:55 NL) vuurde de cron simpelweg niet, ook al was de workflow `state: active`.

**Oplossing:** externe scheduler ([cron-job.org](https://cron-job.org)) die via de GitHub API een `workflow_dispatch` event verstuurt. GitHub honoreert workflow_dispatch events betrouwbaar.

### 11.4 Recent mee gespeeld race condition

De `_voeg_speler_toe()` had ooit een brede XPath-fallback `//*[contains(., 'achternaam') and not(self::input)...]`. Die matchte ook elementen in het "Recent mee gespeeld" paneel — voor spelers die je recent had geboekt stond hun naam alay zichtbaar op de spelers-pagina vóór de typeahead überhaupt loaded.

Resultaat: WebDriverWait zag direct een "match", kandidaten-loop pakte het Recent-element, ActionChains klikte de naam-`<span>` — en omdat dat element een ANDERE click-handler heeft (UI-only update zonder server-AJAX) registreerde de speler nooit server-side. Bij bevestig zei de server dan terecht "Joris niet genoeg spelers".

**Symptomen:** spelers wel verified bij click, maar bij bevestig "niet genoeg spelers". Intermittent — afhankelijk van of Recent-paneel die speler bevat én of typeahead snel genoeg rendert om de specifieke selector eerder match te krijgen.

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

### 11.7 Cron-vroege start vs bevestig-timing

Probleem: cron triggert om 06:50, prep duurt 5 min, dan wacht_at_top tot 07:01, dan bevestig om 07:04 — te laat, slot mogelijk al weg.

**Fix (commit 103493b):** wait-at-top verwijderd; sleep verschoven naar VLAK VOOR bevestig-klik. Prep loopt tijdens de wachttijd, bevestig valt nu op 07:01 NL precies.

### 11.8 ETV "1 actieve reservering"-rule (vermoeden, niet definitief bewezen)

ETV lijkt impliciet geen 2e actieve reservering toe te staan per lid. Symptoom: bij booking-attempt terwijl een andere reservering actief is, kreeg het script terug-redirect naar spelers-pagina. Niet 100% gevalideerd; de Recent-paneel-bug verklaarde mogelijk een aantal van die failures.

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

### Bevestig-timing wijzigen (bv. 07:00 ipv 07:01)

In `boek_baan.py`, in `main()`:
```python
doel_bevestig = boekingsdatum.replace(hour=7, minute=1, ...)
                                              ↑
```

### Cron-tijd wijzigen

In cron-job.org → cronjob → tab Schedule. **Niet** in `verwerk_wachtrij.yml` editen (die schedule is een fallback voor als cron-job.org down is).

### Nieuwe versie van de PWA uitrollen

1. Wijzig `docs/index.html`
2. Bump `CACHE` in `docs/sw.js`:
   ```javascript
   const CACHE = 'padel-v17';   // was v16
   ```
3. Commit + push. GitHub Pages serveert binnen 1-3 min.

### Cron-job.org PAT vernieuwen

Bij PAT-expiry: nieuwe classic PAT met `workflow` scope → cron-job.org → Headers → `Authorization` waarde aanpassen → Save → Test run.

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

Geen `requirements.txt` — pip kiest de versies. Bij Chrome-update kan UC tijdelijk breken; check de `version_main`-detectie in `chrome_major_versie()`.

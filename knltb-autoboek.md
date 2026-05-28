# knltb-autoboek — Volledige documentatie

**GitHub-repository:** `joris-vandenBroek/knltb-autoboek`  
**Doel:** Automatisch een padelbaan reserveren bij ETV Volley via de KNLTB-ledenportal, aangestuurd via een PWA op de telefoon.

---

## Inhoudsopgave

1. [Hoe werkt het in grote lijnen](#1-hoe-werkt-het-in-grote-lijnen)
2. [Repository-structuur](#2-repository-structuur)
3. [Benodigde GitHub Secrets](#3-benodigde-github-secrets)
4. [PWA-frontend — docs/index.html](#4-pwa-frontend--docsindexhtml)
5. [Service Worker — docs/sw.js](#5-service-worker--docsswjs)
6. [GitHub Actions — boek.yml](#6-github-actions--boekyml)
7. [GitHub Actions — haal_leden_op.yml](#7-github-actions--haal_leden_opyml)
8. [boek_baan.py — stap voor stap](#8-boek_baanpy--stap-voor-stap)
9. [haal_leden_op.py — ledenlijst scrapen](#9-haal_leden_oppy--ledenlijst-scrapen)
10. [Technische valkuilen en beslissingen](#10-technische-valkuilen-en-beslissingen)
11. [Wijzigingen aanbrengen](#11-wijzigingen-aanbrengen)

---

## 1. Hoe werkt het in grote lijnen

```
Gebruiker (telefoon)
        │
        │  tikt op "Baan boeken" in de PWA
        ▼
docs/index.html (GitHub Pages PWA)
        │
        │  POST naar GitHub Actions API  (met PAT-token)
        ▼
.github/workflows/boek.yml  (GitHub-hosted runner, ubuntu-latest)
        │
        │  start Python-script met datum/tijd/spelers als argumenten
        ▼
boek_baan.py  (Selenium + undetected-chromedriver + Xvfb)
        │
        │  logt in op etv-volley.nl/mijn
        │  klikt "Baan afhangen"
        │  voegt 3 medespelers toe (typeahead-zoekveld)
        │  selecteert dag + dagdeel (Bootstrap accordion)
        │  selecteert tijdslot (leaf-element)
        │  bevestigt de reservering
        ▼
Google Agenda
        │
        │  schrijft afspraak via Service Account (optioneel)
        ▼
Klaar — gebruiker ontvangt e-mail van ETV Volley
```

De **ledenlijst** (`leden.json`) wordt los bijgehouden via een tweede workflow (`haal_leden_op.yml`) die wekelijks of handmatig draait. Die lijst wordt door de PWA gebruikt voor de speler-dropdowns.

---

## 2. Repository-structuur

```
knltb-autoboek/
├── boek_baan.py               # Hoofdscript: Selenium-boeking
├── haal_leden_op.py           # Script: ledenlijst scrapen naar leden.json
├── leden.json                 # Gesorteerde lijst van alle ETV Volley-leden
├── docs/
│   ├── index.html             # PWA-frontend (GitHub Pages)
│   ├── sw.js                  # Service Worker (offline + caching)
│   ├── manifest.json          # PWA-manifest (installeerbaar op telefoon)
│   ├── logo.png               # ETV Volley logo
│   ├── icon-192.png           # PWA-icoon 192×192
│   └── icon-512.png           # PWA-icoon 512×512
└── .github/
    └── workflows/
        ├── boek.yml           # Workflow: boeking uitvoeren
        └── haal_leden_op.yml  # Workflow: ledenlijst bijwerken
```

GitHub Pages is ingesteld op de `docs/`-map van de `main`-branch. De PWA is daardoor bereikbaar via `https://joris-vandenbroek.github.io/knltb-autoboek/`.

---

## 3. Benodigde GitHub Secrets

In te stellen via **GitHub → Repository → Settings → Secrets and variables → Actions**:

| Secret | Inhoud |
|--------|--------|
| `KNLTB_BONDSNUMMER` | Bondsnummer / gebruikersnaam voor etv-volley.nl |
| `KNLTB_WACHTWOORD` | Wachtwoord voor etv-volley.nl |
| `GOOGLE_CALENDAR_CREDENTIALS` | Volledige JSON-inhoud van het Google Service Account-sleutelbestand |
| `GOOGLE_CALENDAR_ID` | Agenda-ID voor Google Agenda (bijv. `primary` of een e-mailadres) |

Het **GitHub Personal Access Token (PAT)** wordt *niet* als GitHub Secret opgeslagen, maar lokaal in de browser van de gebruiker (`localStorage`). Het PAT heeft de scope `workflow` nodig zodat het workflows kan starten.

---

## 4. PWA-frontend — docs/index.html

Één enkel HTML-bestand, geen frameworks. Werkt als installeerbare web-app (PWA) op iPhone en Android.

### Wat de gebruiker ziet

- **Header** met ETV Volley-logo, titel "Padelbaan Boeken" en een tandwieltje (⚙️) voor het PAT-token.
- **Kaart "Wanneer"** — datumkiezer en tijdkeuze (08:00–21:30, stappen van 30 min, standaard 15:00).
- **Kaart "Medespelers"** — drie dropdowns (speler 2/3/4) met zoekfunctie op de ledenlijst. Speler 1 is altijd "Joris van den Broek" (hardcoded in `boek_baan.py`).
- **Knop "Baan boeken"** — vast onderaan het scherm, triggert de boeking.
- **Toast-melding** — verschijnt onderaan na het drukken (succes of fout).

### Technische details

#### Datum
```javascript
datumBtn.addEventListener('click', function() {
  try { datumInput.showPicker(); } catch (e) { datumInput.click(); }
});
```
`showPicker()` opent de native datepicker op desktop (Chrome 99+). Op mobiel volstaat `.click()`. De `try/catch` zorgt dat het op alle browsers werkt.

#### Tijden
Worden dynamisch gegenereerd: 08:00 t/m 21:30 in stappen van 30 min. Standaard staat 15:00 geselecteerd.

#### Speler-dropdowns (PrimeFaces-stijl)
Zelf gebouwde dropdown met zoekfilter, gemodelleerd naar PrimeFaces `SelectOneMenu`:
- **`togglePf(nr)`** — opent/sluit het panel voor speler 2, 3 of 4.
- **`renderLijst(nr, query)`** — filtert `alleLedenLijst` op de zoekopdracht en bouwt de lijst opnieuw op.
- **`selecteer(nr, naam)`** — slaat naam op in het verborgen `<input id="speler{nr}">` en in `localStorage`. Springt automatisch naar het volgende lege veld.
- **`sluitAlles(uitgezonderd)`** — sluit alle open dropdowns behalve de opgegeven.
- Klikken buiten een dropdown sluit hem (`document.addEventListener('click', ...)`).

Selecties worden opgeslagen in `localStorage` (sleutel `knltb_spelers`) en hersteld bij het opnieuw openen van de app.

#### Ledenlijst
```javascript
const LEDEN_URL = `https://raw.githubusercontent.com/${REPO}/main/leden.json`;

async function laadLeden() {
  const r = await fetch(LEDEN_URL + '?t=' + Date.now());  // cache-busting
  // ...
}
```
Haalt `leden.json` op bij het laden van de app (met cache-busting timestamp). Toont het aantal leden onder de dropdowns. De knop "🔄 Verversen" triggert de `haal_leden_op.yml`-workflow via de GitHub API.

#### Boeking starten
```javascript
const resp = await fetch(
  `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
  { method: 'POST',
    headers: { 'Authorization': `Bearer ${pat}`, ... },
    body: JSON.stringify({ ref: 'main', inputs: { datum, tijd, speler2, speler3, speler4 } })
  }
);
```
Een HTTP 204 betekent dat GitHub de workflow heeft ontvangen. De gebruiker ziet een groene toast. De boeking zelf duurt ~5-10 minuten en eindigt met een e-mail van ETV Volley.

#### PAT-overlay
Verschijnt automatisch als er nog geen PAT opgeslagen is. De PAT wordt opgeslagen in `localStorage` (sleutel `knltb_pat`) — nooit naar een server gestuurd.

#### Validatie
Velden worden rood omlijnd als ze leeg zijn bij het drukken op "Baan boeken". Speler-waarden worden gecontroleerd via de verborgen `<input id="speler{nr}">` (die alleen ingevuld zijn als via de dropdown een keuze gemaakt is).

---

## 5. Service Worker — docs/sw.js

```javascript
const CACHE = 'padel-v10';
```

Elke keer dat `index.html` of `sw.js` inhoudelijk verandert, moet dit versienummer omhoog (bijv. `padel-v11`). De service worker verwijdert dan automatisch de oude cache bij activatie.

### Cachestrategie per bestandstype

| Bestanden | Strategie | Reden |
|-----------|-----------|-------|
| `index.html`, `manifest.json`, `/` | **Network-first**, fallback naar cache | Updates direct zichtbaar |
| `sw.js`, `logo.png`, `icon-192.png`, `icon-512.png` | **Cache-first** | Veranderen zelden |
| `leden.json`, `api.github.com` | **Altijd netwerk**, fallback cache | Altijd vers |
| Overige bestanden | Cache-first | Afbeeldingen/icons |

**Belangrijk:** na een wijziging aan `index.html` moet de cache-versie in `sw.js` verhoogd worden, anders zien gebruikers de oude versie. Sommige browsers updaten de service worker pas na een hard-refresh of na het sluiten en heropenen van de app.

---

## 6. GitHub Actions — boek.yml

**Trigger:** alleen handmatig (`workflow_dispatch`) via de GitHub API (aangestuurd vanuit de PWA).

**Inputs:**

| Input | Beschrijving |
|-------|-------------|
| `datum` | Speeldatum in formaat `YYYY-MM-DD` |
| `tijd` | Voorkeurstijd in formaat `HH:MM` |
| `speler2` | Volledige naam medespeler 2 |
| `speler3` | Volledige naam medespeler 3 |
| `speler4` | Volledige naam medespeler 4 |

**Wat de runner doet:**
1. `actions/checkout@v4` — haalt de code op
2. `actions/setup-python@v5` met Python 3.11
3. `apt-get install xvfb` + `pip install undetected-chromedriver selenium google-api-python-client google-auth`
4. Start Xvfb (virtueel display `:99`) — Chrome draait hierin zonder `--headless`-vlag
5. Voert `boek_baan.py` uit met de invoerparameters

**Bij fout:** uploadt alle `*.png`-screenshots als artifact (3 dagen bewaard) zodat je kunt zien waar het mis ging.

**Timeout:** 15 minuten.

---

## 7. GitHub Actions — haal_leden_op.yml

**Trigger:** handmatig (`workflow_dispatch`) of automatisch elke maandag om 07:00 CEST (`cron: '0 5 * * 1'`).

**Wat de runner doet:**
1. Draait `haal_leden_op.py` (logt in op etv-volley.nl, scrapt de Ledenlijst-tabel)
2. Commit en push het gegenereerde `leden.json` terug naar de repository
3. De PWA pikt de nieuwe lijst op bij de volgende keer laden

**Permissions:** `contents: write` — nodig om `leden.json` terug te kunnen pushen.

---

## 8. boek_baan.py — stap voor stap

### Constanten bovenaan

```python
LOGIN_URL     = "https://www.etv-volley.nl/mijn"
RESERVEER_URL = "https://www.etv-volley.nl/mijn/Reservations"
SPELER1       = "Joris van den Broek"   # altijd speler 1
PADEL_BANEN   = ["Padel 1", ..., "Padel 6"]
```

Credentials komen uit omgevingsvariabelen (GitHub Secrets).

### Hulpfuncties

#### `genereer_tijden(voorkeur_tijd)`
Genereert tijden rondom de voorkeurstijd in stappen van 30 minuten, afwisselend later en eerder: `[15:00, 15:30, 14:30, 16:00, 14:00, ...]`. Stopt bij 08:00 en 22:00. Zo probeert het script bij een vol rooster automatisch een alternatief tijdslot.

#### `dagdeel(tijd)`
Bepaalt of een tijd bij "Ochtend" (< 12:00), "Middag" (12:00–16:59) of "Avond" (≥ 17:00) hoort. Dit wordt gebruikt bij de dag+dagdeel-selectie.

#### `chrome_major_versie()`
Detecteert de geïnstalleerde Chrome-versie via `subprocess` zodat `undetected-chromedriver` exact de bijpassende driver kan downloaden.

#### `maak_driver()`
Maakt een `undetected-chromedriver` (UC) instantie aan **zonder** `--headless`. Chrome draait in een Xvfb-virtueel display. Dit is bewust: Cloudflare detecteert de headless-modus en blokkeert het script.

### STAP 1 — `login()`

1. Navigeert naar `etv-volley.nl/mijn`, wacht 4 seconden (Cloudflare-challenge).
2. Klikt de cookie-banner weg (case-insensitieve XPATH-zoekopdracht).
3. Vult bondsnummer en wachtwoord in via **JavaScript property setter** + `input`/`change` events. Dit triggert ook React/Vue-frameworks die simpele `.value =` assignment negeren.
4. Klikt de submit-knop (zoekt meerdere selectors, fallback: `Keys.RETURN`).
5. Controleert of het wachtwoordveld nog zichtbaar is — zo ja: login mislukt.

### STAP 2 — `klik_baan_afhangen()`

Navigeert naar `etv-volley.nl/mijn/Reservations` en klikt op de "Baan afhangen"-link of knop.

### STAP 3 — `voeg_spelers_toe()` + `_voeg_speler_toe()`

Voor elk van de drie medespelers:

1. **Probeer "Recent mee gespeeld"** — zoekt een `+`-knop naast de naam in een "recent"-sectie.
2. **Typeahead-zoekveld** — typt de naam via `send_keys()` (geen JS-invulling: typeahead reageert alleen op echte toetsaanslagen).
3. **Meerdere zoektermen** — probeert achtereenvolgens:
   - Volledige naam (`"Chris van Waardenburg"`)
   - Voornaam + achternaam zonder tussenvoegsel (`"Chris Waardenburg"`)
   - Alleen achternaam (`"Waardenburg"`)
4. **Wacht op suggestie** — `WebDriverWait(8)` totdat een zichtbaar element de achternaam bevat.
5. **Klik de suggestie** — meerdere XPATH-selectors (role=option, li, div met class player/suggestion/result/item).

### STAP 4 — `kies_dag()`

De dagkeuze-pagina toont een Bootstrap-accordion-grid: kolommen = dagen, rijen = Ochtend/Middag/Avond.

**Probleem met `elementFromPoint`:** het element op het X/Y-snijpunt was de Bootstrap `.collapse`-wrapper, niet de eigenlijke cel. Klikken op die wrapper togglede de accordion maar registreerde geen selectie.

**Oplossing (twee stappen):**

**Stap A — accordion openen:**
```javascript
// Vind dag-header op basis van dag-nummer (tokeniseer "vr 29 mei" → ["vr","29","mei"])
var tokens = (el.innerText || '').trim().split(/\s+/);
tokens.indexOf(dagNr) >= 0 && el.children.length <= 1
// Klik de dag-header → klapt de Bootstrap-accordion open
dagEls[0].click();
```

**Stap B — dagdeel klikken op basis van X-positie:**
```javascript
// Vind alle leaf-elementen met exact de dagdeeltekst ("Ochtend"/"Middag"/"Avond")
txt === dagdeel && el.children.length === 0

// Sorteer op afstand tot de dag-header in X-richting
dagdeelEls.sort(function(a, b) {
    return Math.abs(centerX(a) - dagX) - Math.abs(centerX(b) - dagX);
});
// Klik de dichtstbijzijnde → correcte kolom = correcte dag
```

Tussen stap A en B zit `time.sleep(0.7)` voor de accordeon-animatie.

**Fallback:** als de JS mislukt, klikt Python direct via XPATH het eerste zichtbare dagdeel-element.

### STAP 5 — `kies_baan_en_tijd()`

**Wachtstrategie:** wacht tot `:00` of `:30` voorkomt in de body-tekst. Dit signaleert dat de tijdslot-pagina geladen is. *Niet* wachten op baan-namen (Padel 1 t/m 6): die verschijnen pas nadat een tijdslot geselecteerd is.

**Tijdselectie:**
```javascript
// Verzamel alle kandidaten die beginnen met de gezochte tijd
txt !== tijd && !txt.startsWith(tijd + ' ') && ... continue;

// Sorteer: leaf-elementen (children.length === 0) eerst
// → voorkomt dat een Bootstrap collapse-wrapper geklikt wordt
kandidaten.sort(function(a, b) { return a.children.length - b.children.length; });
kandidaten[0].click();
```

Probeert tijden in de volgorde van `genereer_tijden()`: voorkeur eerst, daarna steeds verder weg.

**Baandetectie:** na het klikken van een tijdslot zoekt de code in de body-tekst naar "Padel 1" t/m "Padel 6". Welke naam er staat = de geboekte baan (het systeem wijst zelf een baan toe).

### STAP 6 — `bevestig()`

Klikt "Volgende" (als aanwezig) en daarna "Bevestig"/"Confirm"/"Boek"/"Reserveer".

### Boekingsdatum-logica in `main()`

ETV Volley opent reserveringen om **07:00 op (speeldatum − 2 kalenderdagen)**. Vanaf dat moment zijn alle dagdelen (ochtend/middag/avond) van de betreffende speeldatum boekbaar. De boekingswindow van het systeem is steeds 3 dagen breed: vandaag (`dag 0`), morgen (`dag+1`) en overmorgen (`dag+2`).

Het script berekent:

```python
boekingsdatum = speeldatum - timedelta(days=2)
dag_verschil  = (speeldatum.date() - nu.date()).days
```

en kiest één van drie gedragsmodi:

| Speeldatum t.o.v. vandaag | Boekingsdatum | Gedrag van script |
|---------------------------|---------------|-------------------|
| `dag 0` (vandaag) of `dag+1` (morgen) | al verstreken | Boekt direct |
| **`dag+2` (overmorgen)** | **vandaag** | Vóór 07:00 → wacht tot 07:00, dan boekt. Na 07:00 → boekt direct |
| **`dag+3` (over 3 dagen)** | **morgen** | Stopt met `⏳ Te vroeg` (`sys.exit(0)`). Workflow moet morgen vóór/op 07:00 opnieuw worden gestart |
| `dag+4` of verder | meer dan 1 dag in toekomst | Stopt met `⏳ Te vroeg` |

De relevante codeflow:

```python
if nu.date() < boekingsdatum.date():
    sys.exit(0)                                # te vroeg → workflow stopt
elif nu.date() == boekingsdatum.date() and nu.hour < 7:
    time.sleep(wacht_sec)                      # wacht tot 07:00 op boekingsdatum
else:
    # boek direct (boekingsdatum bereikt)
```

**Praktische gevolgen:**

- **`dag+2`-boekingen** (meest voorkomend) lopen in één workflow-run: start vóór 07:00 → script wacht → boekt direct na 07:00. De `timeout-minutes: 15` van de runner is voldoende zolang je de workflow niet ruim vóór 06:45 start.
- **`dag+3`-boekingen** vereisen dat je de workflow op de juiste dag start (= 2 kalenderdagen vóór de speeldatum). Tap je vandaag op "Baan boeken" voor een speeldatum over 3 dagen, dan stopt het script met "Te vroeg" en moet je morgen opnieuw drukken. (Alternatief: een vooraf ingestelde `schedule:` in `boek.yml` die om bijv. 06:55 op de boekingsdatum draait.)

### Google Agenda — `voeg_toe_aan_agenda()`

Optioneel (vereist `GOOGLE_CALENDAR_CREDENTIALS` en `GOOGLE_CALENDAR_ID`). Maakt een agenda-afspraak aan via een Service Account (geen OAuth-flow nodig). De afspraak duurt 1 uur, krijgt kleur groen en een popup-herinnering 60 minuten van tevoren.

---

## 9. haal_leden_op.py — ledenlijst scrapen

### Strategie

1. Logt in op `etv-volley.nl/mijn` via dezelfde Selenium/UC/Xvfb-aanpak als `boek_baan.py`.
2. Klikt op de "Ledenlijst"-tab in de navigatie (3 XPATH-selectors als fallback).
3. Scrapt alle namen uit de HTML-tabel (eerste kolom):
   ```javascript
   var rijen = document.querySelectorAll('table tr');
   rijen.forEach(function(rij) {
       var naam = rij.querySelectorAll('td')[0].textContent.trim();
       if (naam.length > 3 && naam.indexOf(' ') >= 0) namen.push(naam);
   });
   ```
   Filtert op: minimaal 4 tekens én bevat een spatie (= voor/achternaam).
4. **Paginering** — klikt door alle pagina's (momenteel ~49):
   - Primair: klik op paginanummer `N+1`
   - Fallback: klik `»` / "Volgende" / `›`
   - Stopt zodra er geen nieuwe namen bijkomen of er geen volgende pagina is
5. **Fallback per letter** — als er na alle pagina's nog geen 10 namen gevonden zijn, doorloopt het script het alfabet en filtert op één letter tegelijk via het zoekfilter.
6. Schrijft het resultaat gesorteerd naar `leden.json`.

### Waarom geen API?

De ETV Volley-website heeft geen publieke API. De ledenlijst is alleen toegankelijk na inloggen op de ledenportal.

### Python `\n` in JavaScript — valkuil

In Python `"""..."""`-strings wordt een backslash-n `\n` een échte newline. In JavaScript-code die je via `execute_script()` doorgeeft, geeft een onverwachte newline een syntax error. Regels om:

- **Nooit** `\n` in regex-tekenklassen: gebruik `/\s+/` of `/\s/`, nooit `/[\s\n]/`
- **Nooit** `\n` in JS-commentaar op dezelfde regel als code
- Multi-line JS is prima zolang de newlines logische regelovergangen zijn

---

## 10. Technische valkuilen en beslissingen

### Cloudflare-omzeiling
`undetected-chromedriver` past de Chrome binary aan zodat Cloudflare-detectie (`navigator.webdriver`) faalt. **Geen `--headless`**: headless-modus laat signatures achter die Cloudflare herkent. Xvfb simuleert een echt scherm.

### Bootstrap accordion vs. `elementFromPoint`
De dagkeuze-pagina gebruikt Bootstrap-accordeons per dag. `document.elementFromPoint(x, y)` gaf het `.collapse`-wrapper-element terug in plaats van de eigenlijke cel. Oplossing: dag-header eerst klikken (accordion openen), daarna de dichtstbijzijnde dagdeel-leaf zoeken op X-coördinaat.

### Leaf-elementen prefereren bij klikken
Zowel voor dagdeel als voor tijdslot: `innerText` van een parent-element bevat alle kindtekst. Een wrapper die "15:00 ..." bevat matcht op "15:00". Oplossing: kandidaten sorteren op `children.length` en de kleinste (leaf) klikken.

### Typeahead vs. JS property setter
Simpele JS-invulling (`el.value = '...'`) werkt niet voor typeahead-velden: de AJAX-call die de suggestielijst ophaalt, wordt niet getriggerd. `send_keys()` simuleert echte toetsaanslagen en triggert de typeahead wel.

### Baan-namen pas zichtbaar na tijdselectie
De namen "Padel 1" t/m "Padel 6" staan pas in de DOM nadat een tijdslot geselecteerd is. Hierop wachten als laadsignaal werkt dus niet. In plaats daarvan wordt gewacht op `:00` of `:30` in de body (tijdslot-rasters).

### Screenshots voor debugging
Elke stap maakt een screenshot: `01_login_pagina.png` t/m `12_na_bevestiging.png`. Bij een gefaald GitHub Actions-run worden deze geüpload als artifact (3 dagen beschikbaar).

---

## 11. Wijzigingen aanbrengen

### Speler 1 wijzigen
In `boek_baan.py`, regel:
```python
SPELER1 = "Joris van den Broek"
```

### Standaard tijd of tijdsbereik wijzigen
In `docs/index.html`:
```javascript
tijdEl.value = '15:00';   // standaard geselecteerde tijd
```
In `boek_baan.py`, `genereer_tijden()`:
```python
vroegst = datetime.strptime("08:00", "%H:%M")
laatst  = datetime.strptime("22:00", "%H:%M")
```

### Nieuwe versie van de PWA uitrollen
1. Wijzig `index.html`.
2. Verhoog de cache-versie in `docs/sw.js`:
   ```javascript
   const CACHE = 'padel-v11';  // was v10
   ```
3. Commit en push — GitHub Pages publiceert automatisch.

### Als de website van ETV Volley verandert

De Selenium-code is opgebouwd met meerdere fallback-selectors, maar als de site een grote redesign krijgt, kunnen stappen falen. Kijk dan in de screenshots (GitHub Actions artifacts) om te zien waar het mis gaat:

| Screenshot | Moment |
|------------|--------|
| `01_login_pagina.png` | Loginpagina geladen |
| `02_na_login.png` | Direct na inloggen |
| `03_reserveer_pagina.png` | Reserveringspagina |
| `04_na_afhangen_klik.png` | Na klikken "Baan afhangen" |
| `05_spelers_pagina.png` | Spelerspagina geladen |
| `05b_zoek_2_*.png` | Tijdens zoeken speler 2/3/4 |
| `06_spelers_toegevoegd.png` | Na toevoegen alle spelers |
| `07_dag_pagina.png` | Dagkeuze-pagina |
| `08_dag_geselecteerd.png` | Na dag + dagdeel selectie |
| `09_baan_pagina.png` | Baan/tijdslot-pagina |
| `10_baan_geselecteerd.png` | Na tijdslotselectie |
| `11_bevestig_pagina.png` | Bevestigingspagina |
| `12_na_bevestiging.png` | Na bevestiging |

### Als de ledenlijst niet meer goed gescraped wordt
Draai `haal_leden_op.yml` handmatig en bekijk de screenshots (`leden-screenshots` artifact). Controleer:
- Is de paginering nog een HTML-tabel met `<tr><td>`?
- Zijn de namen nog in de eerste kolom?
- Is het paginatieformat nog hetzelfde (`« 1 2 3 ... 49 »`)?

Pas `haal_namen_van_pagina()` aan als de tabelstructuur veranderd is.

### Python-dependencies updaten
In `.github/workflows/boek.yml` en `haal_leden_op.yml`:
```yaml
pip install undetected-chromedriver selenium \
            google-api-python-client google-auth
```
Er is geen `requirements.txt` — de versies worden door pip gekozen. Als iets breekt na een Chrome-update, controleer dan de `undetected-chromedriver`-versie.

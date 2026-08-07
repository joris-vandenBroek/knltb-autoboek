# Boekingen van andere gebruikers zien en verwijderen — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Iedereen ziet in de PWA de boekingen van alle gebruikers, en mag naast zijn eigen items ook die van een als `gedeeld` gemarkeerd account (Chris) verwijderen.

**Architecture:** Eén nieuw veld `"gedeeld": true` in `gebruikers.json` en één helper `magVerwijderen(eigenaarId)` in `docs/index.html`. Die helper vervangt de huidige harde `true`/`false` in beide renderpaden. Het annuleren van een reservering krijgt de eigenaar expliciet mee, omdat het nu de geselecteerde gebruiker gebruikt en anders op het verkeerde ETV-account zou inloggen.

**Tech Stack:** Vanilla JavaScript in één statisch HTML-bestand (`docs/index.html`), geen build-tooling, geen JS-testframework. Verificatie via de Browser-tool tegen een lokale `python -m http.server` op `docs/`, met een gemockte of live `gebruikers.json`.

## Global Constraints

- **Dit is geen beveiliging.** Alle gebruikers delen één GitHub-PAT; deze rechten zijn client-side en dus adviserend — een drempel tegen per ongeluk klikken. Bouw er geen aannames op die veiligheid veronderstellen.
- **Regel is symmetrisch:** Joris mag Toine's boekingen net zo min verwijderen als andersom. Bewust gekozen; maak er geen beheerdersrol van.
- **Alleen deze bestanden:** `gebruikers.json`, `docs/index.html`, `docs/sw.js`, plus documentatie. Niet aan `boek_baan.py`, `lees_reserveringen.py` of workflows komen.
- **De beheer-UI (🛠️) houdt zijn eigen `BEHEER_EIGENAAR`-gate.** Die gaat over het toevoegen/verwijderen van *gebruikers*, niet van boekingen. Niet aanpassen.
- **`docs/sw.js` `CACHE` moet omhoog** zodra `docs/index.html` inhoudelijk verandert (`knltb-autoboek.md` sectie 7). Huidige waarde: `'padel-v59'`.
- De PWA laadt `gebruikers.json` van `https://raw.githubusercontent.com/<REPO>/main/gebruikers.json`, **niet** van de lokale server. Een lokaal getest `gedeeld`-veld moet dus al gepusht zijn.

---

### Task 1: `gedeeld`-veld en de rechtenhelper

**Files:**
- Modify: `gebruikers.json`
- Modify: `docs/index.html` (nieuwe helpers, direct ná `laadGebruikers()` op regel 977-985)

**Interfaces:**
- Consumes: `laadGebruikers()` → `Promise<Array<{id, naam, gedeeld?}>>` (bestaand, regel 977), `_gebruikersCache` (module-scope variabele, regel 978), `getGebruiker()` → `string` (bestaand, regel 949).
- Produces, gebruikt door Task 2, 3 en 4:
  - `_isGedeeld(id: string) -> boolean` — synchroon, leest `_gebruikersCache`
  - `magVerwijderen(eigenaarId: string) -> boolean`

- [ ] **Step 1: Zet `gedeeld` op Chris en push meteen**

In `gebruikers.json`, vervang:

```json
  {
    "id": "chris_van_waardenburg",
    "naam": "Chris van Waardenburg"
  }
```

door:

```json
  {
    "id": "chris_van_waardenburg",
    "naam": "Chris van Waardenburg",
    "gedeeld": true
  }
```

Committen en pushen vóór je verder gaat:

```bash
git add gebruikers.json
git commit -m "feat: markeer Chris als gedeeld account"
git push
```

Dit is veilig los van de rest: geen enkele bestaande code leest `gedeeld`, dus het verandert nog niets. Het moet wel op `main` staan, want de PWA haalt `gebruikers.json` van `raw.githubusercontent.com` en niet van je lokale server — anders zie je het veld straks niet tijdens het testen.

- [ ] **Step 2: Voeg de helpers toe**

In `docs/index.html`, direct ná het sluitende accolade van `laadGebruikers()` (regel 985), voeg toe:

```javascript
  /** Is dit een gedeeld account (zoals Chris), dat iedereen mag opruimen? */
  function _isGedeeld(id) {
    const lijst = _gebruikersCache || [];
    const g = lijst.find(x => x.id === id);
    return !!(g && g.gedeeld);
  }

  /**
   * Mag de huidige gebruiker items van `eigenaarId` verwijderen?
   *
   * LET OP: de volgorde van deze twee condities is load-bearing.
   * _gebruikersCache kan null zijn wanneer _renderReservList vanuit
   * laadReserveringen() draait -- die wacht niet op laadGebruikers().
   * De eigen-eigenaarscheck staat daarom vooraan: die heeft de cache niet
   * nodig, dus de knop op je eigen lijst verschijnt hoe dan ook. De
   * _isGedeeld-tak wordt alleen bereikt vanuit laadAndereGebruikers(), dat
   * wel await laadGebruikers() doet voor het renderen.
   */
  function magVerwijderen(eigenaarId) {
    return eigenaarId === getGebruiker() || _isGedeeld(eigenaarId);
  }
```

- [ ] **Step 3: Start de preview en verifieer de helpers**

Gebruik de Browser-tool: `preview_start({ name: "pwa-docs" })`, daarna `navigate({ url: "http://localhost:8730/" })`.

Voer via `javascript_tool` (action `javascript_exec`) exact dit uit:

```javascript
(async () => {
  await laadGebruikers();                       // vult _gebruikersCache
  localStorage.setItem('knltb_gebruiker', 'joris_van_den_broek');
  const alsJoris = {
    eigen:  magVerwijderen('joris_van_den_broek'),
    chris:  magVerwijderen('chris_van_waardenburg'),
    toine:  magVerwijderen('toine_aanraad'),
  };
  localStorage.setItem('knltb_gebruiker', 'toine_aanraad');
  const alsToine = {
    eigen:  magVerwijderen('toine_aanraad'),
    chris:  magVerwijderen('chris_van_waardenburg'),
    joris:  magVerwijderen('joris_van_den_broek'),
  };
  localStorage.setItem('knltb_gebruiker', 'joris_van_den_broek');
  return JSON.stringify({ alsJoris, alsToine });
})()
```

Expected: `{"alsJoris":{"eigen":true,"chris":true,"toine":false},"alsToine":{"eigen":true,"chris":true,"joris":false}}`

- [ ] **Step 4: Verifieer de koude-cache-volgorde**

Dit is de regressie die de spec expliciet noemt. Voer uit:

```javascript
(() => {
  _gebruikersCache = null;                      // simuleer koude cache
  localStorage.setItem('knltb_gebruiker', 'joris_van_den_broek');
  const eigen  = magVerwijderen('joris_van_den_broek');  // moet true blijven
  const gedeeld = magVerwijderen('chris_van_waardenburg'); // mag false zijn
  return JSON.stringify({ eigen, gedeeld });
})()
```

Expected: `{"eigen":true,"gedeeld":false}`

Is `eigen` hier `false`, dan staat `_isGedeeld` vóór de eigen-check en verdwijnt de 🗑️ soms van je eigen lijst. Draai de condities dan om.

- [ ] **Step 5: Commit**

```bash
git add docs/index.html
git commit -m "feat: helper magVerwijderen voor gedeelde accounts"
```

---

### Task 2: Iedereen ziet elkaars boekingen

**Files:**
- Modify: `docs/index.html:1614-1620` (`laadAndereGebruikers`)

**Interfaces:**
- Consumes uit Task 1: `magVerwijderen` (nog niet gebruikt in deze taak), `getGebruiker()`.
- Produces: geen nieuwe functies. Na deze taak toont de sectie voor élke gebruiker de andere gebruikers, nog steeds read-only.

- [ ] **Step 1: Verwijder de gate en pas het filter aan**

In `docs/index.html`, vervang:

```javascript
  async function laadAndereGebruikers() {
    const sectie = document.getElementById('andereGebruikersSection');
    if (getGebruiker() !== BEHEER_EIGENAAR) { sectie.style.display = 'none'; return; }

    const gebruikers = await laadGebruikers();
    const anderen = gebruikers.filter(g => g.id !== BEHEER_EIGENAAR);
```

door:

```javascript
  async function laadAndereGebruikers() {
    const sectie = document.getElementById('andereGebruikersSection');

    const gebruikers = await laadGebruikers();
    // Iedereen ziet iedereen. Je eigen boekingen staan al in de hoofdkaarten,
    // dus die filteren we eruit -- niet BEHEER_EIGENAAR zoals voorheen.
    const anderen = gebruikers.filter(g => g.id !== getGebruiker());
```

- [ ] **Step 2: Verifieer als Toine**

Herlaad de pagina in de Browser-tool (`navigate` naar `http://localhost:8730/` of `javascript_tool`: `window.location.reload()`), en voer daarna uit:

```javascript
(async () => {
  localStorage.setItem('knltb_gebruiker', 'toine_aanraad');
  await laadAndereGebruikers();
  const sectie = document.getElementById('andereGebruikersSection');
  const koppen = [...sectie.querySelectorAll('.card-header')].map(e => e.textContent.trim());
  return JSON.stringify({ zichtbaar: sectie.style.display !== 'none', koppen });
})()
```

Expected: `zichtbaar` is `true` en `koppen` bevat kaarten voor zowel Joris van den Broek als Chris van Waardenburg, en **niet** voor Toine Aanraad zelf.

- [ ] **Step 3: Verifieer als Joris (regressiecheck)**

```javascript
(async () => {
  localStorage.setItem('knltb_gebruiker', 'joris_van_den_broek');
  await laadAndereGebruikers();
  const koppen = [...document.getElementById('andereGebruikersSection')
    .querySelectorAll('.card-header')].map(e => e.textContent.trim());
  return JSON.stringify(koppen);
})()
```

Expected: kaarten voor Toine Aanraad en Chris van Waardenburg, niet voor Joris zelf. Dit is hetzelfde gedrag als vóór de wijziging.

- [ ] **Step 4: Commit**

```bash
git add docs/index.html
git commit -m "feat: alle gebruikers zien elkaars boekingen in de PWA"
```

---

### Task 3: Verwijderknop bij andermans wachtrij-items

**Files:**
- Modify: `docs/index.html:1691-1709` (de wachtrij-render binnen `laadAndereGebruikers`)

**Interfaces:**
- Consumes uit Task 1: `magVerwijderen(eigenaarId) -> boolean`.
- Consumes bestaand: `verwijderWachtrij(btn, path, sha)` (regel 1566) — werkt al op een pad en is gebruiker-agnostisch, dus die hoeft niet aangepast.
- Produces: geen nieuwe functies.

- [ ] **Step 1: Neem `file` mee in de destructuring en render de knop**

De huidige render gooit het `file`-object weg (`entries.map(({ content: c }) => ...)`), waardoor `path` en `sha` niet beschikbaar zijn. Vervang in `docs/index.html`:

```javascript
          el.innerHTML = entries.map(({ content: c }) => {
```

door:

```javascript
          const magWeg = magVerwijderen(g.id);
          el.innerHTML = entries.map(({ file: f, content: c }) => {
```

en vervang binnen diezelfde map-functie:

```javascript
            return `<div class="wachtrij-item${gefaald ? ' wachtrij-failed' : ''}">
              <div class="wachtrij-item-inhoud">
                <div class="wachtrij-datum">${gefaald ? '❌' : '🗓️'} ${datum}</div>
                <div class="wachtrij-spelers">${spelers}</div>
                <div class="wachtrij-boekt">${statusBadge}</div>
              </div>
            </div>`;
```

door:

```javascript
            const delKnop = magWeg
              ? `<button class="wachtrij-del" title="Verwijder deze ingeplande reservering"
                        onclick="verwijderWachtrij(this,'${escapeHtml(f.path)}','${escapeHtml(f.sha)}')">🗑️</button>`
              : '';
            return `<div class="wachtrij-item${gefaald ? ' wachtrij-failed' : ''}">
              <div class="wachtrij-item-inhoud">
                <div class="wachtrij-datum">${gefaald ? '❌' : '🗓️'} ${datum}</div>
                <div class="wachtrij-spelers">${spelers}</div>
                <div class="wachtrij-boekt">${statusBadge}</div>
              </div>
              ${delKnop}
            </div>`;
```

- [ ] **Step 2: Verifieer dat Toine wél bij Chris en niet bij Joris een knop krijgt**

Herlaad de pagina en voer uit:

```javascript
(async () => {
  localStorage.setItem('knltb_gebruiker', 'toine_aanraad');
  await laadAndereGebruikers();
  await new Promise(r => setTimeout(r, 2500));   // wacht op de async per-gebruiker fetches
  const tel = id => document.querySelectorAll(
    `#wachtrijList_${id} button.wachtrij-del`).length;
  return JSON.stringify({
    chris: tel('chris_van_waardenburg'),
    joris: tel('joris_van_den_broek'),
  });
})()
```

Expected: `chris` groter dan 0 (er staan wachtrij-items voor Chris) en `joris` gelijk aan `0`.

Krijg je `chris: 0`, controleer dan eerst of er überhaupt items staan — `document.querySelectorAll('#wachtrijList_chris_van_waardenburg .wachtrij-item').length` moet groter dan 0 zijn. Is dat 0, dan is de fetch mislukt (PAT ingesteld?) en zegt de test niets.

- [ ] **Step 3: Commit**

```bash
git add docs/index.html
git commit -m "feat: verwijderknop bij wachtrij-items van gedeelde accounts"
```

---

### Task 4: Andermans reservering annuleren op het juiste account

**Files:**
- Modify: `docs/index.html:1723` (`_renderReservList`), `docs/index.html:1661` (aanroep in `laadAndereGebruikers`), `docs/index.html:1888-1895` (`annuleerReservering`)

**Interfaces:**
- Consumes uit Task 1: `magVerwijderen(eigenaarId) -> boolean`.
- Consumes bestaand: `_dispatchBeheer(pat, gebruiker, cancelId = '')` → `Promise<boolean>` (regel 1809), `getGebruiker()`.
- Produces:
  - `_renderReservList(items, toonDel = true, eigenaarId = null)` → `string`
  - `annuleerReservering(btn, id, datum, tijd, eigenaarId = null)` → `Promise<void>`

- [ ] **Step 1: Geef `_renderReservList` een eigenaar mee**

In `docs/index.html`, vervang:

```javascript
  function _renderReservList(items, toonDel = true) {
```

door:

```javascript
  function _renderReservList(items, toonDel = true, eigenaarId = null) {
```

en vervang binnen die functie:

```javascript
      const delBtn = toonDel
        ? `<button class="wachtrij-del" title="Annuleer deze reservering"
                  onclick="annuleerReservering(this,'${id}','${escapeHtml(rv.datum)}','${escapeHtml(rv.tijd)}')">🗑️</button>`
        : '';
```

door:

```javascript
      const eig = eigenaarId ? `,'${escapeHtml(eigenaarId)}'` : '';
      const delBtn = toonDel
        ? `<button class="wachtrij-del" title="Annuleer deze reservering"
                  onclick="annuleerReservering(this,'${id}','${escapeHtml(rv.datum)}','${escapeHtml(rv.tijd)}'${eig})">🗑️</button>`
        : '';
```

Zonder `eigenaarId` blijft de gegenereerde onclick exact zoals hij was, dus de bestaande aanroep voor je eigen lijst (regel 1771, `_renderReservList(items)`) verandert niet.

- [ ] **Step 2: Laat `annuleerReservering` de eigenaar gebruiken**

Vervang:

```javascript
  async function annuleerReservering(btn, id, datum, tijd) {
```

door:

```javascript
  async function annuleerReservering(btn, id, datum, tijd, eigenaarId = null) {
```

en vervang binnen die functie:

```javascript
      const r = await _dispatchBeheer(pat, getGebruiker(), id);
```

door:

```javascript
      // Annuleren moet gebeuren op het ETV-account van de EIGENAAR van de
      // reservering, niet op de gebruiker die nu geselecteerd staat. Zonder
      // dit logt de workflow in op het verkeerde account en vindt daar het
      // cancel-ID niet.
      const r = await _dispatchBeheer(pat, eigenaarId || getGebruiker(), id);
```

- [ ] **Step 3: Zet de knop aan bij andere gebruikers**

Vervang in `laadAndereGebruikers` (regel 1661):

```javascript
              : _renderReservList(items, false);
```

door:

```javascript
              : _renderReservList(items, magVerwijderen(g.id), g.id);
```

- [ ] **Step 4: Verifieer dat de dispatch het juiste account meestuurt**

Dit is de enige regressie die stil kan falen. Vang de dispatch af zonder hem echt te versturen:

```javascript
(async () => {
  const origineel = window.fetch;
  let payload = null;
  window.fetch = async (u, opts) => {
    if (String(u).includes('/actions/workflows/')) {
      payload = JSON.parse(opts.body);
      return { status: 204 };
    }
    return origineel(u, opts);
  };
  const nepKnop = document.createElement('button');
  window.confirm = () => true;                 // sla de bevestiging over
  await annuleerReservering(nepKnop, '2026-09-01_2000_padel-1',
                            '2026-09-01', '20:00', 'chris_van_waardenburg');
  window.fetch = origineel;
  return JSON.stringify(payload);
})()
```

Expected: de payload bevat `"gebruiker":"chris_van_waardenburg"` — **niet** de ingelogde gebruiker. Staat er `joris_van_den_broek` of `toine_aanraad`, dan is Step 2 niet goed doorgevoerd.

Let op: dit vereist dat er een PAT is ingesteld, anders stopt de functie bij de `getPat()`-check en blijft `payload` `null`.

- [ ] **Step 5: Verifieer de knoppen in de reserveringslijsten**

```javascript
(async () => {
  localStorage.setItem('knltb_gebruiker', 'toine_aanraad');
  await laadAndereGebruikers();
  await new Promise(r => setTimeout(r, 2500));
  const tel = id => document.querySelectorAll(
    `#reservList_${id} button.wachtrij-del`).length;
  return JSON.stringify({
    chris: tel('chris_van_waardenburg'),
    joris: tel('joris_van_den_broek'),
  });
})()
```

Expected: `joris` is `0`. `chris` is `0` zolang Chris geen actieve reserveringen heeft — controleer dan met `document.querySelectorAll('#reservList_chris_van_waardenburg .wachtrij-item').length` of er überhaupt iets staat. Is dat ook 0, dan zegt deze test niets en volstaat Step 4 als bewijs.

- [ ] **Step 6: Commit**

```bash
git add docs/index.html
git commit -m "feat: annuleer andermans reservering op het juiste ETV-account"
```

---

### Task 5: Service worker en documentatie

**Files:**
- Modify: `docs/sw.js:1`
- Modify: `README.md` (sectie Multi-user setup)
- Modify: `knltb-autoboek.md` (nieuwe subsectie in sectie 13)

**Interfaces:**
- Consumes: alle voorgaande taken.
- Produces: geen code.

- [ ] **Step 1: Verhoog de cache-versie**

In `docs/sw.js`, vervang:

```javascript
const CACHE = 'padel-v59';
```

door:

```javascript
const CACHE = 'padel-v60';
```

Zonder deze bump serveert de service worker de oude `index.html` en zie je je wijziging niet op geïnstalleerde apparaten.

- [ ] **Step 2: Documenteer het `gedeeld`-veld in `README.md`**

Voeg in de sectie "Multi-user setup", direct ná het codeblok met het
`GEBRUIKERS_CONFIG`-voorbeeld en de uitleg over `calendar_id`, toe:

```markdown
### Gedeelde accounts

Een gebruiker die niet zelf boekt maar namens wie anderen boeken, krijgt
`"gedeeld": true` in `gebruikers.json`:

```json
{ "id": "chris_van_waardenburg", "naam": "Chris van Waardenburg", "gedeeld": true }
```

Gevolg in de PWA: **iedereen** mag de boekingen en ingeplande reserveringen van
zo'n account verwijderen. Boekingen van een persoonlijk account (zonder dat
veld) kan alleen de eigenaar zelf weghalen -- symmetrisch, dus ook Joris kan
Toine's boekingen niet verwijderen.

Dit is een drempel tegen per ongeluk klikken, **geen beveiliging**: alle
gebruikers delen hetzelfde GitHub-token en kunnen daarmee via de API alsnog
alles verwijderen.
```

- [ ] **Step 3: Documenteer de valkuil in `knltb-autoboek.md`**

Voeg toe aan het eind van sectie 13. Controleer eerst welk nummer vrij is:

```bash
grep -n "^### 13\." knltb-autoboek.md
```

Gebruik het eerstvolgende vrije nummer en schrijf:

```markdown
### 13.<N> Annuleren gebruikt de eigenaar, niet de geselecteerde gebruiker

`annuleerReservering` in `docs/index.html` riep `_dispatchBeheer(pat,
getGebruiker(), id)` aan -- de gebruiker die op dat moment in de selector staat.
Zolang je alleen je eigen reserveringen kon annuleren klopte dat. Sinds
gedeelde accounts (2026-08) kun je ook die van Chris annuleren, en dan is de
geselecteerde gebruiker de verkeerde: de workflow logt in op jouw ETV-account en
zoekt daar een cancel-ID dat niet bestaat.

De eigenaar wordt daarom expliciet meegegeven:
`annuleerReservering(btn, id, datum, tijd, eigenaarId)`, doorgestuurd naar
`_dispatchBeheer`. Zonder dat argument valt hij terug op `getGebruiker()`, zodat
de eigen lijst ongewijzigd blijft werken.

Dit faalt stil -- de dispatch slaagt (204), de workflow draait, en pas in de
Actions-log zie je dat er niets geannuleerd is. Controleer bij wijzigingen hier
altijd de `gebruiker`-waarde in de dispatch-payload.
```

- [ ] **Step 4: Commit**

```bash
git add docs/sw.js README.md knltb-autoboek.md
git commit -m "docs: gedeelde accounts, plus cache-bump naar v60"
```

---

## Verificatie na afloop

- [ ] **Volledige matrix in de browser**

Herlaad de pagina en loop beide gebruikers langs. Verwacht:

| Als | Eigen lijsten | Chris | De andere persoon |
|-----|---------------|-------|-------------------|
| Joris | 🗑️ zichtbaar | 🗑️ zichtbaar | géén 🗑️ |
| Toine | 🗑️ zichtbaar | 🗑️ zichtbaar | géén 🗑️ |

- [ ] **Python-testsuite draait nog**

Run: `python -m unittest discover -s tests -t .`
Expected: `OK`. Deze taak raakt geen Python, dus een failure hier betekent dat er
iets anders is stukgegaan.

- [ ] **Pages-deploy**

`publiceer_pwa.yml` bouwt alleen bij wijzigingen onder `docs/**`. Die zijn er, dus
er hoort een run te starten na de push. Controleer met:

```bash
gh run list --workflow=publiceer_pwa.yml --limit 1
```

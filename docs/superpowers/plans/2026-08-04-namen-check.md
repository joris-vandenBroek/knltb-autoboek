# Namen-check bij 2e reservering op dezelfde dag — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Voorkom dat de PWA een reservering aanmaakt (direct of via wachtrij) wanneer een van de 4 spelers al in een actieve of ingeplande reservering voor dezelfde speeldatum zit — want die boeking zou bij ETV toch mislukken (vermoedelijke "1 actieve reservering per lid"-regel, zie `knltb-autoboek.md` 13.9).

**Architecture:** Eén nieuwe client-side helper `_vindDubbeleSpelers(datum, nieuweSpelers)` in `docs/index.html` die, over alle gebruikers uit `gebruikers.json` heen, `reserveringen_<id>.json` en `wachtrij/<id>/*.json` doorzoekt op de opgegeven datum en de spelerslijsten daarvan verzamelt. `boekBaan()` roept deze helper aan vóór de `workflow_dispatch`-POST; bij een treffer wordt de boeking afgebroken met een foutmelding via de bestaande `toonToast()`.

**Tech Stack:** Vanilla JavaScript in een enkel statisch HTML-bestand (`docs/index.html`), geen build-tooling, geen testframework. Verificatie gebeurt door de pagina in de browser te laden en functies/flows direct aan te roepen met een gemockte `window.fetch` (zie Testplan in de spec).

## Global Constraints

- Check is **cross-user**: kijkt over alle gebruikers uit `gebruikers.json` heen, niet alleen de gebruiker die nu boekt.
- Check draait **uitsluitend client-side** in `docs/index.html`, vóór de `workflow_dispatch`-aanroep. Geen wijzigingen aan `boek_baan.py`, `lees_reserveringen.py` of workflow-YAML's.
- **Fail-open:** elke fetch-fout (netwerk, 404, parse-fout) bij het ophalen van andermans data wordt genegeerd — de check mag een legitieme boeking nooit blokkeren omdat de check zelf netwerkproblemen had.
- **Gefaalde wachtrij-items** (boekdatum al gepasseerd zonder dat het bestand is opgeruimd) tellen niet mee — anders kan een mislukte boeking nooit opnieuw geprobeerd worden voor dezelfde speeldatum.
- Geen check op duplicaten binnen dezelfde nieuwe reservering — die bestaat al in `valideer()` (`docs/index.html:2100-2105`).
- Volgens `knltb-autoboek.md` sectie 7 moet `docs/sw.js`'s `CACHE`-versienummer omhoog zodra `docs/index.html` inhoudelijk verandert.

---

### Task 1: Helper `_vindDubbeleSpelers` implementeren en isoleerd verifiëren

**Files:**
- Modify: `docs/index.html` (nieuwe functie, vlak vóór `async function boekBaan()` op regel 2122)
- Create: `.claude/launch.json` (lokale statische server om de PWA in de Browser-tool te kunnen laden)

**Interfaces:**
- Consumes: `laadGebruikers()` → `Promise<Array<{id: string, naam: string}>>` (bestaand, regel 977), `getGebruiker()` → `string` (bestaand, regel 949), `getPat()` → `string` (bestaand, regel 972), `minusDagen(isoDatum: string, n: number)` → `string` (ISO-datum, bestaand, regel 1422), `REPO` (const string, regel 940).
- Produces: `async function _vindDubbeleSpelers(datum: string, nieuweSpelers: string[])` → `Promise<string[]>` (lijst van namen uit `nieuweSpelers` die al voorkomen in een bestaande reservering/wachtrij-item op `datum`; lege lijst bij geen match of bij fouten). Gebruikt door Task 2.

- [ ] **Step 1: Maak `.claude/launch.json` voor een lokale preview-server**

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "pwa-docs",
      "runtimeExecutable": "python",
      "runtimeArgs": ["-m", "http.server", "8730", "--directory", "docs"],
      "port": 8730
    }
  ]
}
```

- [ ] **Step 2: Start de preview-server en open de pagina**

Gebruik de Browser-tool: `preview_start({ name: "pwa-docs" })`, daarna `navigate({ url: "http://localhost:8730/" })`.

- [ ] **Step 3: Voer de verificatiescript uit vóórdat de functie bestaat — bevestig dat het faalt**

Voer via de Browser-tool (`javascript_tool`, action `javascript_exec`) exact dit script uit:

```javascript
(async () => {
  try {
    await _vindDubbeleSpelers('2026-09-01', ['Iemand']);
    return 'ONVERWACHT: geen ReferenceError';
  } catch (e) {
    return `VERWACHT: ${e.constructor.name}: ${e.message}`;
  }
})();
```

Expected: het resultaat bevat `ReferenceError` (functie bestaat nog niet).

- [ ] **Step 4: Implementeer `_vindDubbeleSpelers` in `docs/index.html`**

Zoek in `docs/index.html` naar deze regel (rond regel 2121):

```html
  /* ─── Baan reserveren ──────────────────────────────────────── */
  async function boekBaan() {
```

Vervang door (voeg de nieuwe functie ervoor toe):

```html
  /* ─── Namen-check: voorkom 2e reservering met overlappende speler ───
   * ETV staat vermoedelijk maar 1 actieve reservering per lid toe (zie
   * knltb-autoboek.md 13.9). Check over alle gebruikers heen of een van
   * de nieuwe spelers al in een actieve of ingeplande reservering voor
   * dezelfde speeldatum zit. Fail-open: elke fetch-fout wordt genegeerd,
   * de check mag nooit een boeking blokkeren door eigen netwerkproblemen.
   */
  async function _vindDubbeleSpelers(datum, nieuweSpelers) {
    const bestaandeNamen = new Set();
    try {
      const gebruikers = await laadGebruikers();
      const pat = getPat();
      const ghHeaders = pat
        ? { 'Authorization': `Bearer ${pat}`, 'Accept': 'application/vnd.github+json' }
        : { 'Accept': 'application/vnd.github+json' };

      await Promise.all(gebruikers.map(async g => {
        // Actieve reserveringen
        try {
          const r = await fetch(
            `https://raw.githubusercontent.com/${REPO}/main/reserveringen_${g.id}.json?t=${Date.now()}`,
            { cache: 'no-store' }
          );
          if (r.ok) {
            const data = await r.json();
            (data.reserveringen || []).forEach(rv => {
              if (rv.datum === datum && Array.isArray(rv.spelers)) {
                rv.spelers.forEach(n => bestaandeNamen.add(n));
              }
            });
          }
        } catch (_) {}

        // Ingeplande reserveringen (wachtrij), gefaalde items uitgesloten
        try {
          const r = await fetch(
            `https://api.github.com/repos/${REPO}/contents/wachtrij/${g.id}?t=${Date.now()}`,
            { headers: ghHeaders }
          );
          if (r.ok) {
            const files = await r.json();
            const jsons = Array.isArray(files)
              ? files.filter(f => f.name.endsWith('.json') && f.name !== '.gitkeep')
              : [];
            const contents = (await Promise.all(jsons.map(async f => {
              try { const cr = await fetch(f.download_url); return await cr.json(); }
              catch (_) { return null; }
            }))).filter(Boolean);

            const nu = new Date();
            const vandaag = new Date(nu); vandaag.setHours(0, 0, 0, 0);
            const drempel07 = new Date(vandaag); drempel07.setHours(7, 0, 0, 0);

            contents.forEach(c => {
              if (c.datum !== datum) return;
              const boekDatumISO = minusDagen(c.datum, 2);
              const [by, bm, bd] = boekDatumISO.split('-').map(Number);
              const boekDt = new Date(by, bm - 1, bd);
              const gefaald = (boekDt < vandaag) ||
                              (boekDt.getTime() === vandaag.getTime() && nu > drempel07);
              if (gefaald) return;
              (c.spelers || []).forEach(n => bestaandeNamen.add(n));
            });
          }
        } catch (_) {}
      }));
    } catch (e) {
      console.warn('Namen-check mislukt, ga door zonder check:', e);
      return [];
    }
    return nieuweSpelers.filter(n => bestaandeNamen.has(n));
  }

  /* ─── Baan reserveren ──────────────────────────────────────── */
  async function boekBaan() {
```

- [ ] **Step 5: Herlaad de pagina en voer de volledige verificatiescript uit**

Herlaad via `navigate({ url: "http://localhost:8730/" })` (force reload), wacht tot de pagina klaar is, en voer dit script uit via `javascript_tool`:

```javascript
(async () => {
  const results = [];
  function assertEqual(label, actual, expected) {
    const ok = JSON.stringify(actual) === JSON.stringify(expected);
    results.push(`${ok ? 'PASS' : 'FAIL'}: ${label} — kreeg ${JSON.stringify(actual)}, verwacht ${JSON.stringify(expected)}`);
  }

  const echteFetch = window.fetch;
  const MOCK_GEBRUIKERS = [
    { id: 'joris_van_den_broek', naam: 'Joris van den Broek' },
    { id: 'toine_aanraad', naam: 'Toine Aanraad' }
  ];

  function maakMockFetch(scenario) {
    return async (url) => {
      const u = String(url);
      if (u.includes('gebruikers.json')) {
        return { ok: true, json: async () => MOCK_GEBRUIKERS };
      }
      if (u.includes('reserveringen_joris_van_den_broek.json')) {
        return { ok: true, json: async () => ({ reserveringen: [] }) };
      }
      if (u.includes('reserveringen_toine_aanraad.json')) {
        return { ok: true, json: async () => scenario.toineReserveringen || { reserveringen: [] } };
      }
      if (u.includes('/contents/wachtrij/joris_van_den_broek')) {
        return { ok: true, json: async () => scenario.jorisWachtrijFiles || [] };
      }
      if (u.includes('/contents/wachtrij/toine_aanraad')) {
        return { ok: true, json: async () => scenario.toineWachtrijFiles || [] };
      }
      if (u.startsWith('MOCK_DOWNLOAD:')) {
        const key = u.replace('MOCK_DOWNLOAD:', '');
        return { ok: true, json: async () => scenario.downloads[key] };
      }
      throw new Error('Onverwachte fetch in test: ' + u);
    };
  }

  // Scenario A: overlap met actieve reservering van Toine
  _gebruikersCache = null;
  window.fetch = maakMockFetch({
    toineReserveringen: { reserveringen: [
      { datum: '2026-09-01', spelers: ['Toine Aanraad', 'Chris van Waardenburg', 'Peter Nijhof', 'Ellen Daniels'] }
    ]}
  });
  let r = await _vindDubbeleSpelers('2026-09-01', ['Joris van den Broek', 'Chris van Waardenburg', 'Iemand Anders']);
  assertEqual('Scenario A: overlap met actieve reservering', r, ['Chris van Waardenburg']);

  // Scenario B: andere datum, geen overlap
  _gebruikersCache = null;
  window.fetch = maakMockFetch({
    toineReserveringen: { reserveringen: [
      { datum: '2026-09-02', spelers: ['Toine Aanraad', 'Chris van Waardenburg', 'Peter Nijhof', 'Ellen Daniels'] }
    ]}
  });
  r = await _vindDubbeleSpelers('2026-09-01', ['Joris van den Broek', 'Chris van Waardenburg', 'Iemand Anders']);
  assertEqual('Scenario B: andere datum geen match', r, []);

  // Scenario C: gefaald wachtrij-item met overlap -> mag NIET blokkeren
  _gebruikersCache = null;
  window.fetch = maakMockFetch({
    toineWachtrijFiles: [{ name: '2020-01-05_1500.json', download_url: 'MOCK_DOWNLOAD:gefaald' }],
    downloads: { gefaald: { datum: '2020-01-05', spelers: ['Toine Aanraad', 'Chris van Waardenburg', 'Peter Nijhof', 'Ellen Daniels'] } }
  });
  r = await _vindDubbeleSpelers('2020-01-05', ['Joris van den Broek', 'Chris van Waardenburg', 'Iemand Anders']);
  assertEqual('Scenario C: gefaald wachtrij-item blokkeert niet', r, []);

  // Scenario D: niet-gefaald wachtrij-item met overlap -> moet blokkeren
  _gebruikersCache = null;
  const toekomst = new Date(); toekomst.setDate(toekomst.getDate() + 10);
  const toekomstIso = `${toekomst.getFullYear()}-${String(toekomst.getMonth()+1).padStart(2,'0')}-${String(toekomst.getDate()).padStart(2,'0')}`;
  window.fetch = maakMockFetch({
    toineWachtrijFiles: [{ name: 'x.json', download_url: 'MOCK_DOWNLOAD:actief' }],
    downloads: { actief: { datum: toekomstIso, spelers: ['Toine Aanraad', 'Chris van Waardenburg', 'Peter Nijhof', 'Ellen Daniels'] } }
  });
  r = await _vindDubbeleSpelers(toekomstIso, ['Joris van den Broek', 'Chris van Waardenburg', 'Iemand Anders']);
  assertEqual('Scenario D: actief wachtrij-item blokkeert wel', r, ['Chris van Waardenburg']);

  // Scenario E: fetch faalt volledig -> fail-open, geen exception
  _gebruikersCache = null;
  window.fetch = async () => { throw new Error('gesimuleerde netwerkfout'); };
  let threw = false, r5 = null;
  try { r5 = await _vindDubbeleSpelers('2026-09-01', ['Joris van den Broek']); }
  catch (e) { threw = true; }
  assertEqual('Scenario E: fail-open bij netwerkfout (geen exception)', threw, false);
  assertEqual('Scenario E: fail-open geeft lege lijst', r5, []);

  window.fetch = echteFetch;
  return results.join('\n');
})();
```

Expected: alle 6 regels beginnen met `PASS`. Als er een `FAIL`-regel tussen zit, herbekijk de implementatie van Step 4 voordat je verder gaat.

- [ ] **Step 6: Commit**

```bash
git add docs/index.html .claude/launch.json
git commit -m "feat: voeg _vindDubbeleSpelers helper toe voor namen-check per dag"
```

---

### Task 2: `_vindDubbeleSpelers` inhaken in `boekBaan()`, SW-versie bumpen, end-to-end verifiëren

**Files:**
- Modify: `docs/index.html:2141-2143` (aanroep helper direct na `datumNL`-berekening in `boekBaan()`)
- Modify: `docs/sw.js:1` (cache-versie ophogen, verplicht bij elke inhoudelijke `index.html`-wijziging — zie `knltb-autoboek.md` sectie 7)

**Interfaces:**
- Consumes: `_vindDubbeleSpelers(datum, nieuweSpelers)` uit Task 1, `laadGebruikers()`, `getGebruiker()`, `toonToast(type, tekst)` (bestaand), `minusDagen` (bestaand, indirect via Task 1).
- Produces: niets voor latere tasks — dit is de laatste task.

- [ ] **Step 1: Wijzig `boekBaan()` om de helper aan te roepen**

Zoek in `docs/index.html` naar (rond regel 2141-2144):

```html
    const [_y, _m, _d] = datum.split('-');
    const datumNL = `${_d}-${_m}-${_y}`;

    // Bepaal of dit een directe reservering is of een ingeplande (dag+3 of verder).
```

Vervang door:

```html
    const [_y, _m, _d] = datum.split('-');
    const datumNL = `${_d}-${_m}-${_y}`;

    const gebruikersVoorCheck = await laadGebruikers();
    const eigenGebruiker = gebruikersVoorCheck.find(g => g.id === getGebruiker());
    const eigenNaam = eigenGebruiker ? eigenGebruiker.naam : '';
    const nieuweSpelers = [eigenNaam, speler2, speler3, speler4].filter(Boolean);

    const dubbeleNamen = await _vindDubbeleSpelers(datum, nieuweSpelers);
    if (dubbeleNamen.length > 0) {
      const namenTekst = dubbeleNamen.join(', ');
      const werkwoord = dubbeleNamen.length === 1 ? 'staat' : 'staan';
      toonToast('error',
        `⚠️ ${namenTekst} ${werkwoord} al (in)gepland op ${datumNL}. Een speler kan niet in 2 reserveringen op dezelfde dag zitten.`);
      btn.disabled = false;
      document.getElementById('btnTekst').textContent =
        dryRun ? '🧪  Dry-run baan reserveren' : '🎾  Baan reserveren';
      return;
    }

    // Bepaal of dit een directe reservering is of een ingeplande (dag+3 of verder).
```

- [ ] **Step 2: Bump de service worker cache-versie**

In `docs/sw.js`, regel 1, wijzig:

```javascript
const CACHE = 'padel-v58';
```

naar:

```javascript
const CACHE = 'padel-v59';
```

- [ ] **Step 3: Herlaad de preview en voer de end-to-end verificatiescript uit — scenario met blokkade**

Herlaad `http://localhost:8730/` (force reload zodat de gewijzigde `index.html` geladen wordt). Voer via `javascript_tool` dit script uit:

```javascript
(async () => {
  const results = [];
  function assertEqual(label, actual, expected) {
    const ok = JSON.stringify(actual) === JSON.stringify(expected);
    results.push(`${ok ? 'PASS' : 'FAIL'}: ${label} — kreeg ${JSON.stringify(actual)}, verwacht ${JSON.stringify(expected)}`);
  }

  localStorage.setItem('knltb_pat', 'dummy-token-voor-test');
  localStorage.setItem('knltb_gebruiker', 'joris_van_den_broek');

  datumInput.value = '2026-09-01';
  if (![...tijdEl.options].some(o => o.value === '15:00')) {
    const opt = document.createElement('option'); opt.value = '15:00'; opt.textContent = '15:00';
    tijdEl.appendChild(opt);
  }
  tijdEl.value = '15:00';
  const sportEl = document.getElementById('sport');
  if (![...sportEl.options].some(o => o.value === 'padel')) {
    const opt = document.createElement('option'); opt.value = 'padel'; opt.textContent = 'Padel';
    sportEl.appendChild(opt);
  }
  sportEl.value = 'padel';
  document.getElementById('speler2').value = 'Chris van Waardenburg';
  document.getElementById('speler3').value = 'Peter Nijhof';
  document.getElementById('speler4').value = 'Ellen Daniels';

  const MOCK_GEBRUIKERS = [
    { id: 'joris_van_den_broek', naam: 'Joris van den Broek' },
    { id: 'toine_aanraad', naam: 'Toine Aanraad' }
  ];

  let dispatchAangeroepen = false;
  const echteFetch = window.fetch;
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (u.includes('gebruikers.json')) return { ok: true, json: async () => MOCK_GEBRUIKERS };
    if (u.includes('reserveringen_joris_van_den_broek.json')) return { ok: true, json: async () => ({ reserveringen: [] }) };
    if (u.includes('reserveringen_toine_aanraad.json')) {
      return { ok: true, json: async () => ({ reserveringen: [
        { datum: '2026-09-01', spelers: ['Toine Aanraad', 'Chris van Waardenburg', 'Peter Nijhof', 'Ellen Daniels'] }
      ]})};
    }
    if (u.includes('/contents/wachtrij/')) return { ok: true, json: async () => [] };
    if (u.includes('/dispatches')) { dispatchAangeroepen = true; return { status: 204 }; }
    throw new Error('Onverwachte fetch: ' + u);
  };

  _gebruikersCache = null;
  await boekBaan();
  window.fetch = echteFetch;

  assertEqual('Blokkade-scenario: workflow NIET getriggerd', dispatchAangeroepen, false);
  assertEqual('Blokkade-scenario: knop weer enabled', document.getElementById('boekBtn').disabled, false);

  return results.join('\n');
})();
```

Expected: beide regels `PASS`. Controleer daarnaast visueel (via `screenshot` of `get_page_text`) dat de rode foutmelding-toast de tekst "Chris van Waardenburg" bevat.

- [ ] **Step 4: Voer de end-to-end verificatiescript uit — scenario zonder overlap (moet doorgaan)**

Voer via `javascript_tool` dit script uit (zelfde pagina-state, geen reload nodig):

```javascript
(async () => {
  const results = [];
  function assertEqual(label, actual, expected) {
    const ok = JSON.stringify(actual) === JSON.stringify(expected);
    results.push(`${ok ? 'PASS' : 'FAIL'}: ${label} — kreeg ${JSON.stringify(actual)}, verwacht ${JSON.stringify(expected)}`);
  }

  document.getElementById('boekBtn').disabled = false;
  datumInput.value = '2026-09-01';
  document.getElementById('speler2').value = 'Chris van Waardenburg';
  document.getElementById('speler3').value = 'Peter Nijhof';
  document.getElementById('speler4').value = 'Ellen Daniels';

  const MOCK_GEBRUIKERS = [
    { id: 'joris_van_den_broek', naam: 'Joris van den Broek' },
    { id: 'toine_aanraad', naam: 'Toine Aanraad' }
  ];

  let dispatchAangeroepen = false;
  const echteFetch = window.fetch;
  window.fetch = async (url) => {
    const u = String(url);
    if (u.includes('gebruikers.json')) return { ok: true, json: async () => MOCK_GEBRUIKERS };
    if (u.includes('reserveringen_joris_van_den_broek.json')) return { ok: true, json: async () => ({ reserveringen: [] }) };
    if (u.includes('reserveringen_toine_aanraad.json')) {
      return { ok: true, json: async () => ({ reserveringen: [
        { datum: '2026-09-05', spelers: ['Toine Aanraad', 'Chris van Waardenburg', 'Peter Nijhof', 'Ellen Daniels'] }
      ]})};
    }
    if (u.includes('/contents/wachtrij/')) return { ok: true, json: async () => [] };
    if (u.includes('/dispatches')) { dispatchAangeroepen = true; return { status: 204 }; }
    throw new Error('Onverwachte fetch: ' + u);
  };

  _gebruikersCache = null;
  await boekBaan();
  window.fetch = echteFetch;

  assertEqual('Geen-overlap-scenario: workflow WEL getriggerd', dispatchAangeroepen, true);

  return results.join('\n');
})();
```

Expected: `PASS`. Dit bevestigt dat de check normale boekingen niet blokkeert (datum van Toine's reservering is hier `2026-09-05`, de nieuwe boeking is voor `2026-09-01` — geen match).

- [ ] **Step 5: Stop de preview-server**

Gebruik de Browser-tool: `preview_stop` met de `serverId` uit Step 2 van Task 1.

- [ ] **Step 6: Commit**

```bash
git add docs/index.html docs/sw.js
git commit -m "feat: blokkeer 2e reservering bij overlappende spelersnaam op dezelfde dag"
```

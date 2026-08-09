// Draait de ECHTE baankeuze-JS uit boek_baan.py tegen een nagebouwd ETV-grid.
//
// Bestaansreden: die JS is het kwetsbaarste stuk van de repo en werd nergens
// gedekt. Commit e9a76b1 (07-08-2026) brak daardoor onopgemerkt het kiezen van
// ELKE padelbaan; dat kwam pas twee dagen later boven water toen twee
// padelboekingen faalden. Deze harness draait zonder browser of netwerk.
//
// Aanroep: node baankeuze_harness.js <pad-naar-geextraheerde-js>
const fs = require('fs');
const js = fs.readFileSync(process.argv[2], 'utf8');

// Minimale DOM met precies de API's die de JS gebruikt. Bouwt de knop na zoals
// ETV hem levert:
//   <button class="btn-link">9 Padel 1<span>Padel</span></button>
// dus een tekstnode gevolgd door een span. textContent plakt die aan elkaar tot
// "9 Padel 1Padel" -- precies de reden dat een naieve replace('Padel','') de
// VERKEERDE treffer weghaalt.
function maakCourt(kopTekst, sportLabel, vrijeTijden) {
  const tekstNode = { nodeType: 3, textContent: kopTekst };
  const span = { nodeType: 1, textContent: sportLabel };
  const btn = {
    childNodes: [tekstNode, span],
    textContent: kopTekst + sportLabel,
    querySelector: (sel) => (sel === 'span' ? span : null),
  };
  return {
    querySelector: (sel) => (sel === 'button.btn-link' ? btn : null),
    querySelectorAll: (sel) => {
      if (sel !== '.timeincourt:not(.disabled)') return [];
      return vrijeTijden.map((t) => ({ innerText: t }));
    },
  };
}

function run(courts, tijd, sport, voorkeur) {
  const window = {};
  const document = {
    querySelectorAll: (sel) => (sel === '.court' ? courts : []),
  };
  const fn = new Function('document', 'window', 'a0', 'a1', 'a2',
    'var arguments=[a0,a1,a2];' + js);
  const res = fn(document, window, tijd, sport, voorkeur);
  return { gekozen: res ? res.baan : null, kandidaten: window._kiesBaanKandidaten };
}

// Grid met 6 padelbanen (1 en 2 bezet), 2 tennisbanen en een pickle-baan.
const grid = [
  maakCourt('9 Padel 1', 'Padel', []),
  maakCourt('10 Padel 2', 'Padel', []),
  maakCourt('11 Padel 3', 'Padel', ['20:00']),
  maakCourt('12 Padel 4', 'Padel', ['20:00']),
  maakCourt('13 Padel 5', 'Padel', ['20:00']),
  maakCourt('14 Padel 6', 'Padel', ['20:00']),
  maakCourt('1 04', 'Smashcourt', ['20:00']),
  maakCourt('8 12', 'Smashcourt', ['20:00']),
  maakCourt('15 Pickle 1', 'Hardcourt', ['20:00']),
];

const P = (n) => 'Padel ' + n;
const voorkeuren = {
  joris: [P(3), P(4), P(5), P(6), P(1), P(2)],
  toine: [P(5), P(6), P(1), P(2), P(3), P(4)],
  chris: [P(1), P(2), P(3), P(4), P(5), P(6)],
};

let fouten = 0;
function check(naam, actueel, verwacht) {
  const ok = actueel === verwacht;
  if (!ok) fouten++;
  console.log(`${ok ? 'OK  ' : 'FOUT'} ${naam}: ${actueel}${ok ? '' : ` (verwacht ${verwacht})`}`);
}

// Regressie e9a76b1: hierop gaf de kapotte parser null voor elke padelbaan.
// Chris' voorkeur begint bij Padel 1, maar 1 en 2 zijn bezet in dit grid,
// dus Padel 3 is zijn eerste beschikbare.
check('padel wordt uberhaupt herkend',
  run(grid, '20:00', 'padel', voorkeuren.chris).gekozen, 'Padel 3');

// Elk account start op een andere baan (zie boek_regels.baan_voorkeur).
check('joris start op eigen baan', run(grid, '20:00', 'padel', voorkeuren.joris).gekozen, 'Padel 3');
check('toine start op eigen baan', run(grid, '20:00', 'padel', voorkeuren.toine).gekozen, 'Padel 5');
check('joris en toine botsen niet',
  String(run(grid, '20:00', 'padel', voorkeuren.joris).gekozen
      !== run(grid, '20:00', 'padel', voorkeuren.toine).gekozen), 'true');

// Tennis blijft hoogste baan eerst (commit e9a76b1, baan 04 is de slechtste).
const tennisVoorkeur = ['Tennis 12', 'Tennis 11', 'Tennis 09', 'Tennis 08',
                        'Tennis 07', 'Tennis 06', 'Tennis 05', 'Tennis 04'];
check('tennis kiest hoogste baan',
  run(grid, '20:00', 'tennis', tennisVoorkeur).gekozen, 'Tennis 12');

// Pickle 1 heeft span 'Hardcourt' en mag er niet tussendoor glippen.
check('pickle-baan telt niet mee als padel',
  String(run([maakCourt('15 Pickle 1', 'Hardcourt', ['20:00'])],
             '20:00', 'padel', voorkeuren.joris).gekozen), 'null');

// indexOf geeft -1 voor een baan buiten de voorkeurslijst; zonder correctie
// zou zo'n onbekende baan juist als eerste gekozen worden.
check('onbekende baan sorteert achteraan',
  run([maakCourt('20 Padel 9', 'Padel', ['20:00']), maakCourt('11 Padel 3', 'Padel', ['20:00'])],
      '20:00', 'padel', voorkeuren.joris).gekozen, 'Padel 3');

// Bezette banen leveren geen cellen op.
check('alles bezet geeft niets',
  String(run([maakCourt('9 Padel 1', 'Padel', []), maakCourt('10 Padel 2', 'Padel', [])],
             '20:00', 'padel', voorkeuren.joris).gekozen), 'null');

console.log(fouten === 0 ? '\nALLE JS-CHECKS OK' : `\n${fouten} JS-CHECK(S) GEFAALD`);
process.exit(fouten === 0 ? 0 : 1);

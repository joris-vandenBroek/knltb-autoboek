# Wekelijks terugkerende reserveringen

**Datum:** 2026-08-07
**Status:** Approved

## Probleem

Er is geen enkele vorm van herhaling in knltb-autoboek. Een wachtrij-item
(`wachtrij/<gebruiker>/<datum>_<tijd>.json`) is altijd eenmalig. Wie elke week
op hetzelfde moment wil spelen, moet elke week met de hand nieuwe items
aanmaken.

Concrete aanleiding: elke dinsdag om 20:00 één tennisbaan onder Chris van
Waardenburg en twee padelbanen onder Toine Aanraad en Joris van den Broek —
drie boekingen per week, met 12 vaste spelers.

## Doel

Een declaratieve herhaalregel die zichzelf uitvoert, zonder dat de bestaande
boekflow verandert. De regels materialiseren zich als gewone wachtrij-items,
zodat alle bestaande logica (retry-strategie rond 07:00, uitwijken naar een
alternatieve tijd, opruiming na succes, foutmelding in de PWA) ongewijzigd
blijft gelden.

## Scope

**Wel:**
- `herhalingen.json` met de herhaalregels, plus validatie daarvan
- `genereer_herhalingen.py` + `genereer_herhalingen.yml` die wachtrij-items
  vooruit aanmaken
- Vervaltermijn voor wachtrij-items met een speeldatum in het verleden

**Niet:**
- Beheer van herhaalregels via de PWA. Bij 12 vaste spelers pas je dit hooguit
  een paar keer per jaar aan; een edit in de repo volstaat. (YAGNI)
- Bewerken van individuele wachtrij-items. Een afwijkende week los je op door
  het item te verwijderen en zo nodig opnieuw te boeken via de gewone flow.
- Wijzigingen aan `boek.yml`, `verwerk_wachtrij.yml` of `boek_baan.py`.

## Ontwerp

### 1. `herhalingen.json`

Nieuw bestand in de repo-root, naast `gebruikers.json`. Niet-gevoelig.

```json
[
  {
    "id": "dinsdag-tennis-chris",
    "actief": true,
    "weekdag": "dinsdag",
    "tijd": "20:00",
    "sport": "tennis",
    "gebruiker": "chris_van_waardenburg",
    "spelers": ["Chris van Waardenburg", "…", "…", "…"],
    "gegenereerd_tot": "2026-08-11"
  }
]
```

Drie regels: tennis onder Chris, padel onder Toine, padel onder Joris.

`spelers[0]` is de boeker zelf. Dat komt overeen met het formaat van bestaande
wachtrij-items; `verwerk_wachtrij.yml` leest alleen `spelers[1..3]`, omdat
speler 1 uit `SPELER1_NAAM` in `GEBRUIKERS_CONFIG` komt.

`gegenereerd_tot` wordt door de generator beheerd — niet met de hand aanpassen,
behalve om bewust opnieuw te laten genereren.

### 2. Validatie

De generator valideert álle regels voordat hij iets schrijft, en faalt hard
(exit 1, dus workflow-failure + issue) bij een overtreding:

| Check | Waarom |
|---|---|
| `gebruiker` bestaat in `gebruikers.json` | Anders faalt `boek.yml` pas op de boekdag met "niet gevonden in GEBRUIKERS_CONFIG" |
| Alle 4 namen staan letterlijk in `leden.json` | Vangt een typefout in een spelersnaam nú, in plaats van zondag 07:00 als mislukte boeking |
| Precies 4 spelers, `spelers[0]` == naam van de boeker | `boek.yml` vereist `speler2/3/4`; een afwijkend aantal breekt de dispatch |
| Geen naam komt in twee regels voor op dezelfde weekdag | Dit is de cross-booking namen-check uit de PWA (zie `2026-08-04-namen-check-design.md`), die een generator anders zou omzeilen |
| `sport` is `padel` of `tennis`, `tijd` matcht `HH:MM` | Ongeldige waarden bereiken anders de Selenium-flow |

De namen-check is hier bewust een *harde* fout en geen waarschuwing: bij een
herhaling zou een stille overtreding zich elke week herhalen.

### 3. Generator

`genereer_herhalingen.py`, aangeroepen door `genereer_herhalingen.yml`.

Per actieve regel:
1. Bereken alle voorkomens van `weekdag` in het venster
   `[max(gegenereerd_tot + 1 dag, vandaag + 3 dagen), vandaag + 4 weken]`

   De ondergrens is *niet* simpelweg `gegenereerd_tot + 1`. Staat een regel een
   tijd op `actief: false` of loopt de generator een periode niet, dan ligt de
   watermark ver in het verleden en zou dat voorkomens in het verleden
   opleveren. Ook `vandaag + 1` is te krap: `verwerk_wachtrij.yml` triggert een
   item op `datum − 2` om 06:50, dus een item voor overmorgen kan die trigger
   al gemist hebben en blijft dan onaangeraakt staan tot het vervalt. Vandaar
   minimaal `vandaag + 3`.
2. Schrijf voor elk voorkomen `wachtrij/<gebruiker>/<datum>_<tijdslug>.json` in
   het bestaande formaat (`gebruiker`, `datum`, `tijd`, `sport`, `spelers`,
   `ingediend`), tenzij het bestand al bestaat
3. Zet `gegenereerd_tot` op de laatst aangemaakte datum

Daarna één commit met de nieuwe wachtrij-items én het bijgewerkte
`herhalingen.json`. `gegenereerd_tot` schuift alleen op voor items die
daadwerkelijk zijn weggeschreven, zodat een halverwege afgebroken run bij de
volgende poging gewoon verdergaat.

**Schedule:** wekelijks via GitHub's eigen cron. Dit is expliciet *niet*
tijdkritisch — het venster is dagen breed — dus hier is de onbetrouwbaarheid
van GitHub cron (zie `knltb-autoboek.md` 13.3) geen bezwaar en is cron-job.org
niet nodig, anders dan bij de 07:00-boeking.

### 4. Waarom een verwijderd item niet terugkomt

`gegenereerd_tot` is een watermark: **de generator kijkt nooit achteruit.** Hij
maakt alleen voorkomens ná die datum aan.

Verwijder je een item voor een vakantieweek, dan ligt die datum al achter de
watermark en wordt hij nooit opnieuw aangemaakt. Zonder dit mechanisme zou de
generator elke week keurig alle verwijderde items terugzetten, en kun je nooit
een week overslaan.

De bestaandheidscheck in stap 2 is dus niet het mechanisme dat verwijderen
respecteert — die vangt alleen dubbele runs binnen hetzelfde venster op.

### 5. Vervaltermijn voor oude wachtrij-items

Uitbreiding van `ruim_wachtrij_op()` in `lees_reserveringen.py` (draait al
dagelijks na elke scrape): verwijder wachtrij-items waarvan `datum` vóór
vandaag ligt, ongeacht of ze matchen met een reservering.

**Why:** opruiming gebeurt nu puur op match met een actieve reservering. Faalt
een boeking, dan blijft het bestand eeuwig staan en toont de PWA het permanent
als rode ❌. Bij een wekelijkse herhaling stapelt dat op tot de geplande-lijst
voornamelijk uit dode regels bestaat — precies de zichtbaarheid die de reden
was om voor wachtrij-items te kiezen.

**Termijn:** de dag ná de speeldatum. De ❌ verschijnt op de boekdag
(speeldatum − 2) en blijft staan tot en met de speeldatum zelf — het venster
waarin je nog handmatig een baan kunt zoeken. Daarna is hij zinloos.

De GitHub-issue die `boek.yml` bij een mislukking opent blijft als vangnet
staan; die wordt hier niet aangeraakt.

## Bediening

| Wat | Hoe |
|---|---|
| Week overslaan | 🗑️ op het geplande item in de PWA. Komt niet terug (watermark). |
| Langer stoppen | `actief: false` op de regel. Stopt nieuwe generatie, laat ingeplande items staan. |
| Spelers wijzigen | Pas `spelers` aan in `herhalingen.json`. Geldt vanaf de eerstvolgende generatie; al ingeplande items houden de oude namen. |
| Opnieuw genereren | `gegenereerd_tot` terugzetten en de workflow handmatig draaien. |

## Risico's

### ETV "1 actieve reservering per lid"

`knltb-autoboek.md` 13.9 vermoedt dat ETV geen tweede actieve reservering per
lid toestaat. Niet gevalideerd.

Als het klopt, legt een vaste wekelijkse dinsdag beslag op de enige
reserveringsplek van alle 12 spelers, van zondagochtend (boekmoment) tot
dinsdagavond. Een van die 12 die in dat venster iets anders wil boeken, botst
daarop — in beide richtingen: de andere boeking faalt, óf de dinsdagboeking
faalt omdat iemand al bezet is.

De drie dinsdagboekingen onderling raken dit niet: 12 verschillende namen
betekent precies één reservering per persoon. De validatie op dubbele namen
bewaakt dat.

Dit is een operationele consequentie, geen ontwerpfout — er is binnen dit
systeem geen mitigatie voor. Bewust geaccepteerd op 2026-08-07.

### Opeenstapeling van issues

Elke mislukte boeking opent een issue (`boek.yml`, `if: failure()`). Bij drie
boekingen per week loopt dat sneller op dan nu. Er staan al 5 open issues,
waarvan 3 mislukte boekingen sinds eind juni. Buiten scope gelaten; de
vervaltermijn uit sectie 5 raakt alleen de wachtrij-items, niet de issues.

## Openstaand voor implementatie

De 12 spelersnamen zijn nog niet bekend — in het voorbeeld hierboven staan ze
als `…`. Per regel zijn 4 namen nodig, exact zoals ze in `leden.json` staan,
met de boeker op positie 0. Zonder die namen kan `herhalingen.json` niet
worden ingevuld en faalt de validatie. De rest van de implementatie (generator,
validatie, vervaltermijn, tests) hangt hier niet van af.

## Testen

- **Generator, unit:** datumberekening per weekdag over maand- en jaargrenzen;
  watermark schuift correct op; bestaand bestand wordt niet overschreven; een
  datum vóór de watermark wordt niet opnieuw aangemaakt.
- **Validatie:** elk van de vijf checks faalt op een preparaat dat precies die
  regel overtreedt, en slaagt op een geldige config.
- **Vervaltermijn:** item met `datum` gisteren wordt verwijderd; item met
  `datum` vandaag blijft staan; item met `datum` morgen blijft staan.
- **End-to-end:** genereer met een regel voor overmorgen, controleer dat
  `verwerk_wachtrij.yml` het item oppikt en `boek.yml` dispatcht. Uitvoeren met
  `dry_run=true` zodat er geen echte reservering ontstaat.

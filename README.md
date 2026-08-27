# ETV Volley Baan Auto-Reservering

Volledig automatische baan-reservering (padel of tennis) bij ETV Volley via de KNLTB-portal -- aangestuurd via een mobiele PWA, draaiend op GitHub Actions, met Google Agenda-koppeling.

**Werkmap:** `C:\Projecten\ETV-Volley\knltb-autoboek` (verplaatst hierheen op 2026-08-27 vanaf `L:\ETV-Volley\knltb-autoboek` / `\\MyCloudEX2Ultra\Transmission\ETV-Volley\knltb-autoboek`, wat nu alleen nog de back-up-bestemming is -- zie `scripts/backup.ps1`; werk niet meer op L:).
Let op: dit project stond daarvoor lokaal in OneDrive (`OneDrive - Pinkroccade\Documents 1\knltb-autoboek`) -- ook die map is leeg en niet meer in gebruik.

**Highlights:**
- Mobiele PWA voor 1-tik-reserveren (padel én tennis)
- Auto-reserveert vanaf 07:00:10 NL op de reserveringsdatum (10s buffer na slot-opening, herprobeert 6x met 10s interval)
- Wachtrij voor reserveringen die nog te ver in de toekomst liggen (TTL 60 dagen)
- Overzicht van actieve reserveringen + annuleren vanuit de app
- Automatische Google Agenda-events: aangemaakt voor alle reserveringen (ook als je medespeler bent), automatisch verwijderd bij annuleren of als een reservering buiten de app om wordt geannuleerd
- Race-conditie-bestendig: als iemand anders net sneller dezelfde baan claimt, probeert het script automatisch de volgende vrije padelbaan (max 6 pogingen)
- Namen-check: voorkomt een 2e reservering op dezelfde dag als een speler al in een bestaande (actieve of ingeplande) reservering zit -- die zou bij ETV toch mislukken
- Dry-run modus: end-to-end test (login + spelers + dag + baan-keuze) zonder echte reservering bij ETV
- Auto-issue bij failure + dead-man's-switch (Healthchecks.io optioneel) + PAT-expiry badge in PWA

---

## Mobiele app

Gehost als Progressive Web App op GitHub Pages.

**URL:** `https://joris-vandenbroek.github.io/knltb-autoboek/`

**Installeren op je telefoon:**
- **Android** (Chrome/Samsung Internet): drie puntjes -> "Toevoegen aan beginscherm"
- **iPhone** (Safari): deel-icoon -> "Zet op beginscherm"

**Eerste keer openen:** voer je GitHub Personal Access Token in via het tandwiel-icoon -- wordt alleen lokaal op je telefoon opgeslagen.

### Kaarten in de PWA

1. **Wanneer** -- datumkiezer + tijdkeuze (08:00-21:30, stappen van 30 min) + Sport-selector (Padel/Tennis)
2. **Medespelers** -- 3 dropdowns met zoekfilter op de ledenlijst
3. **Mijn reserveringen** -- actieve ETV-reserveringen, met knop per item om te annuleren (agenda-event wordt bij eerstvolgende scrape verwijderd). Toont direct de laatste cache; bij data >15 min oud wordt op de achtergrond automatisch ververst. Ook bij elke tab-terugkomst
4. **Ingeplande reserveringen** -- wachtrij voor toekomstige reserveringen, met knop om te verwijderen
5. **Baan reserveren** -- knop vast onderaan, triggert direct of zet in wachtrij. Checkt vooraf of een speler al in een andere reservering voor diezelfde dag zit

---

## Bestanden

| Bestand | Wat doet het? |
|---------|---------------|
| `boek_baan.py` | Hoofdscript -- login, baan + tijd selecteren, bevestigen. Ondersteunt padel én tennis, `--dry-run` |
| `etv_common.py` | Gedeelde ETV-login flow (gebruikt door lees_reserveringen + haal_leden_op) |
| `lees_reserveringen.py` | Scrape actieve reserveringen + annuleren + Google Agenda synchronisatie (aanmaken + verwijderen) |
| `haal_leden_op.py` | Scrape de ledenlijst -> `leden.json` |
| `haal_padel_sterktes.py` | Haal padel speelsterktes op van mijnknltb.toernooi.nl -> `leden.json` |
| `leden.json` | Cache van alle ETV-leden met padel speelsterktes (autocomplete bron voor PWA) |
| `gebruikers.json` | Lijst van actieve gebruikers met ID en naam (niet-gevoelig, in repo) |
| `herhalingen.json` | Wekelijks terugkerende reserveringen (weekdag, tijd, sport, boeker, 4 spelers). `gegenereerd_tot` wordt door de generator beheerd |
| `genereer_herhalingen.py` | Maakt wachtrij-items aan uit `herhalingen.json` -- alleen stdlib, geen dependencies |
| `wachtrij_regels.py` | Gedeelde datum- en padlogica rond wachtrij-items (gebruikt door de generator en `lees_reserveringen.py`) |
| `tests/` | Unittests (stdlib `unittest`). Draaien met `python -m unittest discover -s tests -t .` |
| `reserveringen_<gebruiker>.json` | Cache van actieve reserveringen per gebruiker (bijv. `reserveringen_joris.json`) |
| `wachtrij/<gebruiker>/*.json` | Reserveringen per gebruiker voor speeldatums verder dan dag+2 weg |
| `agenda_items_<gebruiker>.json` | Mapping van reservering-ID naar Google Agenda event-ID (voor idempotente sync en directe verwijdering) |
| `docs/` | PWA-bronbestanden (index.html, sw.js, manifest.json, icons) |
| `.github/workflows/boek.yml` | Voert een reservering uit (getriggerd door PWA of wachtrij) |
| `.github/workflows/verwerk_wachtrij.yml` | Werkt 's ochtends 07:00 NL de wachtrij af |
| `.github/workflows/beheer_reserveringen.yml` | Scrape of annuleer een reservering -- dagelijks 07:30 NL + vanuit PWA |
| `.github/workflows/haal_leden_op.yml` | Wekelijkse ledenlijst-refresh (maandag 07:00) -- triggert daarna automatisch haal_padel_sterktes.yml |
| `.github/workflows/haal_padel_sterktes.yml` | Haal padel speelsterktes op via mijnknltb.toernooi.nl (getriggerd na ledenlijst-refresh) |
| `.github/workflows/publiceer_pwa.yml` | Deployt `docs/` naar GitHub Pages -- alleen bij wijzigingen onder `docs/**`, niet bij elke commit |
| `.github/workflows/genereer_herhalingen.yml` | Genereert wekelijks (maandag 06:00 NL) wachtrij-items uit `herhalingen.json` |

---

## Eenmalige setup

### 1. GitHub Secrets

Ga naar: **Settings -> Secrets and variables -> Actions -> New repository secret**

#### ETV Volley (etv-volley.nl)

ETV Volley credentials worden beheerd via `GEBRUIKERS_CONFIG` (zie hieronder). Losse `ETVVOLLEY_BONDSNUMMER`/`ETVVOLLEY_WACHTWOORD` secrets zijn niet meer nodig.

#### mijnKNLTB (mijnknltb.toernooi.nl)

| Secret | Waarde |
|--------|--------|
| `KNLTB_LOGINNAAM` | Gebruikersnaam voor mijnknltb.toernooi.nl |
| `KNLTB_WACHTWOORD` | Wachtwoord voor mijnknltb.toernooi.nl |

#### Overig

| Secret | Waarde |
|--------|--------|
| `GOOGLE_CALENDAR_CREDENTIALS` | Inhoud van het service-account JSON-bestand (zie hieronder) |
| `GOOGLE_CALENDAR_ID` | Agenda-ID, bijv. `joris.vandenbroek@gmail.com` of `primary` |
| `HEALTHCHECK_PING_URL` *(optioneel)* | Healthchecks.io check URL, bv. `https://hc-ping.com/<uuid>`. Verwerk_wachtrij pingt aan begin + succes + fail. Healthchecks.io stuurt alert na 24u stilte -- dead-man's-switch tegen PAT-verloop / cron-job.org account-issues |

### 2. Google Calendar Service Account (eenmalig, ~10 min)

1. Ga naar [console.cloud.google.com](https://console.cloud.google.com)
2. Maak een nieuw project aan (bijv. "Padel Boeker")
3. Zoek **"Google Calendar API"** -> klik **Inschakelen**
4. **IAM & Beheer -> Serviceaccounts -> Serviceaccount aanmaken** (naam: `padel-boeker`)
5. Klik op het serviceaccount -> tabblad **Sleutels** -> **Sleutel toevoegen -> JSON** -> download
6. Open **Google Agenda** op je computer -> naast jouw agenda -> **Instellingen en delen**
   - Onder **Personen met toegang** -> **Personen uitnodigen**
   - Plak het e-mailadres uit `"client_email"` van het JSON-bestand
   - Geef rol **"Afspraken beheren"** (editor)
7. Kopieer de volledige JSON-inhoud -> plak als `GOOGLE_CALENDAR_CREDENTIALS`-secret

### 3. Externe cron-trigger via cron-job.org (~5 min)

GitHub Actions' eigen scheduled triggers zijn onbetrouwbaar (kunnen volledig overgeslagen worden). Gebruik een externe scheduler.

1. Maak een **classic GitHub PAT** op [github.com/settings/tokens/new](https://github.com/settings/tokens/new):
   - Scope: alleen `workflow`
   - Expiration: bv. 1 jaar
2. Account op [cron-job.org](https://cron-job.org) -> Create cronjob:
   - **URL:** `https://api.github.com/repos/joris-vandenBroek/knltb-autoboek/actions/workflows/verwerk_wachtrij.yml/dispatches`
   - **Schedule:** Every day at **06:50**, timezone **Europe/Amsterdam**
   - **Request method:** POST
   - **Request body:** `{"ref":"main"}`
   - **Request headers:**
     | Name | Value |
     |---|---|
     | `Authorization` | `Bearer ghp_...` (je nieuwe PAT) |
     | `Accept` | `application/vnd.github+json` |
     | `X-GitHub-Api-Version` | `2022-11-28` |
     | `Content-Type` | `application/json` |
3. Test run -> moet **204 No Content** geven

---

## Hoe het werkt

```
1. Open de PWA op je telefoon
2. Kies datum, tijd, sport (Padel of Tennis) en 3 medespelers
3. Tik op "Baan reserveren"
```

Het script kiest op basis van de speeldatum automatisch een van de paden:

| Speeldatum t.o.v. vandaag | Wat er gebeurt |
|---|---|
| **dag 0 / dag+1 / dag+2** | `boek.yml` boekt direct -- binnen 5 min mail van ETV Volley; agenda-event aangemaakt bij eerstvolgende Verversen |
| **dag+3 of verder** | `boek_baan.py` schrijft `wachtrij/<datum>_<tijd>.json` en commit/pusht. Cron-job.org triggert om 06:50 NL op de reserveringsdatum -> boek.yml met die inputs |

### Timing op de reserveringsdatum

De reserveringsdatum is **(speeldatum - 2 kalenderdagen)**. ETV opent het slot om 07:00 NL. Het script doet:

```
06:50:00  cron-job.org POST -> verwerk_wachtrij start
06:51:00  triggert boek.yml
06:51:00  boek_baan.py: login + spelers (klaar ruim voor 07:00)
07:00:01  Dag-selectie poging 1 (max 150 pogingen, 0,15s cooldown, deadline 07:03:00)
07:0x:xx  Dag-selectie geslaagd → direct Baan/tijd-selectie + Volgende
07:0x:xx  BEVESTIG-KLIK + Verificatie
```

Login + spelers gebeurt ruim voor 07:00. Vanaf 07:00:01 wordt dag-keuze geprobeerd -- ETV's server weigert daypart-selectie doorgaans nog zo'n 1-2 minuten na 07:00 (gezien in run #174: pas rond 07:01:30-07:02:30 geaccepteerd). Het script blijft daarom goedkoop doorproberen (~4s per volledige cyclus, geen screenshots meer per poging) tot 07:03:00 in plaats van na een korte deadline te escaleren naar een volledige wizard-herstart. Alleen als de dag-selectie zelf om een andere reden faalt (bv. spelers-pagina weggevallen) volgt een outer-retry; die kost wél een vaste 30s buffer, maar alleen als spelers opnieuw ingevoerd moeten worden -- als spelers al vaststaan wordt direct doorgegaan zonder die 30s. Na een geslaagde dag-selectie volgt de rest van de wizard direct zonder extra wachttijd.

**Baankeuze-volgorde.** Bij meerdere vrije banen op de gewenste tijd kiest het script:

| Sport | Volgorde | Waarom |
|-------|----------|--------|
| Padel | Padel 1 → 6 (laagste eerst) | Ongewijzigd sinds het begin |
| Tennis | 12 → 11 → 09 → ... → 04 (hoogste eerst) | Baan 4 is de slechtste baan en werd door de DOM-volgorde altijd als eerste gekozen. Baan 10 bestaat niet |

De log toont per boekpoging `Vrije banen op voorkeursvolgorde: ...`, zodat te controleren is welke banen vrij waren en in welke volgorde ze zijn overwogen. Zie [knltb-autoboek.md sectie 13.18](knltb-autoboek.md#1318-baankeuze-volgorde-en-de-raw-string-valkuil).

**Race-conditie afhandeling.** Als iemand anders net sneller dezelfde baan + tijd claimt (~1-2 sec venster tussen kies en bevestig), reageert ETV met "niet gevonden" / "al gereserveerd". Het script detecteert dit, navigeert terug naar de baan-keuze pagina + forceert een refresh (ETV toont bezette tijdcellen daarna niet meer), en probeert de volgende vrije baan voor dezelfde tijd. Pas als alle banen op die tijd weg zijn, valt 'ie terug op alternatieve tijden binnen hetzelfde dagdeel (Ochtend/Middag/Avond). Max 6 pogingen totaal. Zie [knltb-autoboek.md sectie 11.11](knltb-autoboek.md#1111-race-conditie-andere-boeker-pakt-de-baan-tussen-kies-en-bevestig).

### Mijn reserveringen / annuleren

In de PWA-kaart "Mijn reserveringen":
- **Automatisch** -> elke ochtend om 07:30 NL scrapet `beheer_reserveringen.yml` alle gebruikers parallel; verlopen of door anderen geannuleerde reserveringen verdwijnen vanzelf uit agenda
- **🔄 Verversen** -> één dispatch met `gebruiker='alle'` triggert alle gebruikers tegelijk via matrix-strategie; de PWA pollt daarna elke 15s (eerste check na 5s) tot de JSON bijgewerkt is
- **🗑️ per reservering** -> annuleert op ETV-site + verwijdert agenda-event

De PWA haalt bij elke open, bij terugkomen in de app en elke 3 minuten de laatste `reserveringen_<gebruiker>.json` op van GitHub (snelle fetch, geen workflow). De 🔄 Verversen-knop en de dagelijkse cron zijn de enige momenten dat de ETV-site opnieuw gescrapet wordt.

**Google Agenda:** alleen aangemaakt voor gebruikers met een eigen `calendar_id` in `GEBRUIKERS_CONFIG`. Medegebruikers zonder eigen agenda-ID maken geen events aan in elkaars agenda.

---

## Ledenlijst en padel speelsterktes bijhouden

`leden.json` wordt elke maandag 07:00 NL automatisch bijgewerkt via `haal_leden_op.yml`. Daarna worden automatisch de padel speelsterktes opgehaald van mijnknltb.toernooi.nl via `haal_padel_sterktes.yml`.

Handmatig:
- **In de app:** tik Verversen onderin de spelers-sectie
- **GitHub:** Actions -> Ledenlijst ophalen -> Run workflow
- **Alleen padel sterktes:** Actions -> Padel speelsterktes ophalen -> Run workflow

De PWA toont onder het ledenaantal "Laatst ververst op DD-MM-YYYY".

---

## Problemen?

| Probleem | Oplossing |
|----------|-----------|
| Reservering mislukt | Actions -> rode run -> download `screenshots`-artifact voor foutdiagnose |
| `Joris niet genoeg spelers` bij bevestig | Race in spelers-selectie. Code matcht nu strict op typeahead-row. Mocht het terugkomen: zie diagnose-logregels `SPELERS-CHECK` per stap |
| Log meldt `Onverwachte speler in #youPlayWith` + `Verwijderd` | Klopt -- defensieve cleanup. ETV's typeahead voegde een speler met overlappende naam toe. Het script ruimt die op en gaat door |
| Rode badge op tandwiel-icoon in PWA | Je GitHub PAT verloopt binnen 7 dagen (of is al verlopen). Genereer nieuwe op github.com/settings/tokens (scope `workflow`) -> tandwiel -> vul in + nieuwe verloopdatum |
| Automatisch issue `auto-failure,boek` in repo | Workflow `boek.yml` faalde. Check link in het issue voor de run-log + download screenshots-artifact. Sluit issue na onderzoek (volgende failure = nieuw issue) |
| Log toont `Padel X was bezet door iemand anders` | Klopt -- race-conditie, script probeert automatisch volgende vrije baan. Eindigt 'ie alsnog met OK: alles goed. Eindigt 'ie met fout na 6 pogingen: alle banen op alle alternatieve tijden (binnen hetzelfde dagdeel) waren bezet (zeldzaam) |
| Wachtrij-item niet verwerkt | Check Actions -> Verwerk Wachtrij. Cron-job.org kan ook 401 geven -> PAT-scope checken |
| Afspraak niet in agenda | Events worden aangemaakt bij de volgende Verversen in de PWA of de dagelijkse cron om 07:30. Controleer ook of agenda gedeeld is met het serviceaccount en of `GOOGLE_CALENDAR_CREDENTIALS` correct is |
| Naam niet gevonden in autocomplete | Tik Verversen om de ledenlijst bij te werken |
| App vraagt PAT | Voer GitHub PAT in via tandwiel (eenmalig per apparaat, scope `workflow` is genoeg) |
| Annuleren werkt niet | Check beheer_reserveringen log. Als ETV-annulering slaagt wordt agenda-event direct verwijderd. Als ETV-annulering mislukt blijft het agenda-event bewust staan. |
| Padel sterktes niet bijgewerkt | Check Actions -> Padel speelsterktes ophalen. Controleer `KNLTB_LOGINNAAM` en `KNLTB_WACHTWOORD` secrets |
| PWA toont oude versie na een wijziging in `docs/` | Check Actions -> Publiceer PWA. Bouwt alleen bij wijzigingen onder `docs/**` -- geen run gestart betekent dat de commit `docs/` niet raakte. Handmatig opnieuw draaien kan via "Run workflow" |

---

## Multi-user setup

Meerdere ETV-leden kunnen dezelfde repo gebruiken. Credentials staan in één GitHub Secret (`GEBRUIKERS_CONFIG`), de gebruikerslijst in `gebruikers.json` (niet-gevoelig, in repo).

### Secret aanmaken

Ga naar **Settings → Secrets and variables → Actions** en maak `GEBRUIKERS_CONFIG` aan met:

```json
{
  "joris_van_den_broek":   { "bondsnummer": "1234567", "wachtwoord": "...", "naam": "Joris van den Broek", "calendar_id": "..." },
  "toine_aanraad":         { "bondsnummer": "7654321", "wachtwoord": "...", "naam": "Toine Aanraad" },
  "chris_van_waardenburg": { "bondsnummer": "8765432", "wachtwoord": "...", "naam": "Chris van Waardenburg" }
}
```

De sleutel is het **gebruiker-ID** uit `gebruikers.json` (naam in kleine letters, spaties vervangen door `_`). `calendar_id` is optioneel -- zonder dat veld worden er geen Google Agenda-events aangemaakt voor die gebruiker.

### Gedeelde accounts

Een gebruiker die niet zelf boekt maar namens wie anderen boeken, krijgt `"gedeeld": true` in `gebruikers.json`:

```json
{ "id": "chris_van_waardenburg", "naam": "Chris van Waardenburg", "gedeeld": true }
```

Gevolg in de PWA: **iedereen** mag de reserveringen en ingeplande reserveringen van zo'n account verwijderen. Boekingen van een persoonlijk account (zonder dat veld) kan alleen de eigenaar zelf weghalen — symmetrisch, dus ook Joris kan Toine's boekingen niet verwijderen.

Dit is een drempel tegen per ongeluk klikken, **geen beveiliging**: alle gebruikers delen hetzelfde GitHub-token en kunnen daarmee via de API alsnog alles verwijderen.

### Gebruiker toevoegen

1. Open de PWA → 🛠️ → wachtwoord `etv2025` → vul ID en naam in → Toevoegen  
   _(of pas `gebruikers.json` rechtstreeks aan in de repo)_
2. Voeg de credentials toe aan het `GEBRUIKERS_CONFIG` secret
3. Maak map `wachtrij/<id>/` aan in de repo (leeg bestand `.gitkeep` voldoet)

### Hoe het werkt (multi-user)

- `boek.yml` / `beheer_reserveringen.yml` / `verwerk_wachtrij.yml` krijgen `gebruiker` als input
- Credentials worden per run gelezen uit `GEBRUIKERS_CONFIG` via `jq`
- Data-isolatie: `reserveringen_<gebruiker>.json` + `wachtrij/<gebruiker>/`
- PWA: gebruiker-selector in ⚙️ Instellingen; alle workflow-dispatches sturen `gebruiker` mee
- Concurrency per gebruiker: `knltb-account-<gebruiker>` / `knltb-beheer-<gebruiker>`

---

## Terugkerende reserveringen

`herhalingen.json` beschrijft reserveringen die elke week terugkomen. Elke maandagochtend maakt `genereer_herhalingen.yml` daaruit wachtrij-items aan voor de komende 4 weken; daarna verloopt alles via de normale wachtrij-flow. Aan `boek.yml`, `verwerk_wachtrij.yml` en `boek_baan.py` verandert niets.

```json
[
  {
    "id": "dinsdag-padel-joris",
    "actief": true,
    "weekdag": "dinsdag",
    "tijd": "20:00",
    "sport": "padel",
    "gebruiker": "joris_van_den_broek",
    "spelers": ["Joris van den Broek", "…", "…", "…"],
    "gegenereerd_tot": "2026-09-01"
  }
]
```

`spelers[0]` is altijd de boeker zelf, met exact de naam uit `gebruikers.json`. `gegenereerd_tot` wordt door de generator beheerd -- niet met de hand aanpassen, behalve om bewust opnieuw te laten genereren.

### Bediening

| Wat | Hoe |
|-----|-----|
| Eén week overslaan | 🗑️ op het geplande item in de PWA. Komt niet terug: de generator kijkt nooit vóór `gegenereerd_tot` |
| Langer stoppen | `actief: false` op de regel. Stopt nieuwe generatie, laat ingeplande items staan |
| Spelers wijzigen | Pas `spelers` aan. Geldt vanaf de eerstvolgende generatie; al ingeplande items houden de oude namen |
| Opnieuw genereren | `gegenereerd_tot` terugzetten en de workflow handmatig draaien |

### Validatie

De generator controleert vóór hij iets schrijft, en faalt hard (exit 1) bij een fout: gebruiker moet in `gebruikers.json` staan, alle 4 spelersnamen letterlijk in `leden.json`, `spelers[0]` moet de boeker zijn, sport `padel` of `tennis`, tijd `HH:MM`, en geen speler mag in twee regels op dezelfde weekdag voorkomen (ETV staat geen 2e actieve reservering per lid toe -- zie `knltb-autoboek.md` 13.9). Zonder die check zou een typefout in een naam zich elke week herhalen.

### Let op

Een vaste wekelijkse reservering legt beslag op de enige reserveringsplek van alle betrokken spelers, van de boekdag (speeldatum -2) tot de speeldatum zelf. Wie in dat venster iets anders wil boeken, botst daarop.

---

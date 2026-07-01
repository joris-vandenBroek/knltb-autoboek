# ETV Volley Baan Auto-Reservering

Volledig automatische baan-reservering (padel of tennis) bij ETV Volley via de KNLTB-portal -- aangestuurd via een mobiele PWA, draaiend op GitHub Actions, met Google Agenda-koppeling.

**Lokale locatie:** `\\MyCloudEX2Ultra\Transmission\ETV-Volley\knltb-autoboek` (ook bereikbaar als `L:\ETV-Volley\knltb-autoboek`).
Let op: dit project stond eerder lokaal in OneDrive (`OneDrive - Pinkroccade\Documents 1\knltb-autoboek`) -- dat is verplaatst naar de NAS. Start nieuwe sessies/tools vanaf het NAS-pad hierboven, niet vanaf de oude OneDrive-map (die is leeg).

**Highlights:**
- Mobiele PWA voor 1-tik-reserveren (padel én tennis)
- Auto-reserveert vanaf 07:00:10 NL op de reserveringsdatum (10s buffer na slot-opening, herprobeert 6x met 10s interval)
- Wachtrij voor reserveringen die nog te ver in de toekomst liggen (TTL 60 dagen)
- Overzicht van actieve reserveringen + annuleren vanuit de app
- Automatische Google Agenda-events: aangemaakt voor alle reserveringen (ook als je medespeler bent), automatisch verwijderd bij annuleren of als een reservering buiten de app om wordt geannuleerd
- Race-conditie-bestendig: als iemand anders net sneller dezelfde baan claimt, probeert het script automatisch de volgende vrije padelbaan (max 6 pogingen)
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
5. **Baan reserveren** -- knop vast onderaan, triggert direct of zet in wachtrij

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
| `reserveringen_<gebruiker>.json` | Cache van actieve reserveringen per gebruiker (bijv. `reserveringen_joris.json`) |
| `wachtrij/<gebruiker>/*.json` | Reserveringen per gebruiker voor speeldatums verder dan dag+2 weg |
| `agenda_items_<gebruiker>.json` | Mapping van reservering-ID naar Google Agenda event-ID (voor idempotente sync en directe verwijdering) |
| `docs/` | PWA-bronbestanden (index.html, sw.js, manifest.json, icons) |
| `.github/workflows/boek.yml` | Voert een reservering uit (getriggerd door PWA of wachtrij) |
| `.github/workflows/verwerk_wachtrij.yml` | Werkt 's ochtends 07:00 NL de wachtrij af |
| `.github/workflows/beheer_reserveringen.yml` | Scrape of annuleer een reservering -- dagelijks 07:30 NL + vanuit PWA |
| `.github/workflows/haal_leden_op.yml` | Wekelijkse ledenlijst-refresh (maandag 07:00) -- triggert daarna automatisch haal_padel_sterktes.yml |
| `.github/workflows/haal_padel_sterktes.yml` | Haal padel speelsterktes op via mijnknltb.toernooi.nl (getriggerd na ledenlijst-refresh) |

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
06:52:00  boek_baan.py: login + spelers (~3-4 min)
06:55:00  klaar voor dag-keuze, sleep tot 07:00:10
07:00:10  Dag-selectie poging 1 (max 6 pogingen, 10s interval)
07:00:10  Dag-selectie geslaagd → direct Baan/tijd-selectie + Volgende
07:00:40  BEVESTIG-KLIK
07:01:10  Verificatie
```

Login + spelers gebeurt tijdens de wachttijd voor 07:00. Vanaf 07:00:10 (10s buffer voor klok-skew) wordt dag-keuze geprobeerd -- ETV's server weigert daypart-selectie voor 07:00. Bij mislukken: 5 herhalingen met 10s ertussen. Na een geslaagde dag-selectie volgt de rest van de wizard direct zonder extra wachttijd.

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

---

## Multi-user setup

Meerdere ETV-leden kunnen dezelfde repo gebruiken. Credentials staan in één GitHub Secret (`GEBRUIKERS_CONFIG`), de gebruikerslijst in `gebruikers.json` (niet-gevoelig, in repo).

### Secret aanmaken

Ga naar **Settings → Secrets and variables → Actions** en maak `GEBRUIKERS_CONFIG` aan met:

```json
{
  "joris": { "bondsnummer": "1234567", "wachtwoord": "...", "naam": "Joris van den Broek" },
  "toine": { "bondsnummer": "7654321", "wachtwoord": "...", "naam": "Toine Aanraad" }
}
```

### Gebruiker toevoegen

1. Open de PWA → 🛠️ → wachtwoord `etv2025` → vul ID en naam in → Toevoegen  
   _(of pas `gebruikers.json` rechtstreeks aan in de repo)_
2. Voeg de credentials toe aan het `GEBRUIKERS_CONFIG` secret
3. Maak map `wachtrij/<id>/` aan in de repo (leeg bestand `.gitkeep` voldoet)

### Hoe het werkt

- `boek.yml` / `beheer_reserveringen.yml` / `verwerk_wachtrij.yml` krijgen `gebruiker` als input
- Credentials worden per run gelezen uit `GEBRUIKERS_CONFIG` via `jq`
- Data-isolatie: `reserveringen_<gebruiker>.json` + `wachtrij/<gebruiker>/`
- PWA: gebruiker-selector in ⚙️ Instellingen; alle workflow-dispatches sturen `gebruiker` mee
- Concurrency per gebruiker: `knltb-account-<gebruiker>` / `knltb-beheer-<gebruiker>`

---

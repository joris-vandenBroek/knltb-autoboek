# 🎾 ETV Volley Padelbaan Auto-Reservering

Volledig automatische padelbaan-reservering bij ETV Volley via de KNLTB-portal — aangestuurd via een mobiele PWA, draaiend op GitHub Actions, met Google Agenda-koppeling.

**Highlights:**
- 📱 Mobiele PWA voor 1-tik-reserveren
- 🤖 Auto-reserveert vanaf 07:01 NL op de reserveringsdatum (1 min na slot-opening tegen klok-skew)
- 📥 Wachtrij voor reserveringen die nog te ver in de toekomst liggen
- 📅 Overzicht van actieve reserveringen + 🗑️ annuleren vanuit de app
- 🗓️ Automatische Google Agenda-events (toegevoegd bij reserveren, verwijderd bij annuleren)

---

## 📱 Mobiele app

Gehost als Progressive Web App op GitHub Pages.

**URL:** `https://joris-vandenbroek.github.io/knltb-autoboek/`

**Installeren op je telefoon:**
- **Android** (Chrome/Samsung Internet): drie puntjes → "Toevoegen aan beginscherm"
- **iPhone** (Safari): deel-icoon → "Zet op beginscherm"

**Eerste keer openen:** voer je GitHub Personal Access Token in via ⚙️ — wordt alleen lokaal op je telefoon opgeslagen.

### Kaarten in de PWA

1. **Wanneer** — datumkiezer + tijdkeuze (08:00–21:30, stappen van 30 min)
2. **Medespelers** — 3 dropdowns met zoekfilter op de ledenlijst
3. **📅 Mijn reserveringen** — actieve ETV-reserveringen, met 🗑️ knop per item om te annuleren (haalt ook agenda-event weg)
4. **🕒 Ingeplande reserveringen** — wachtrij voor toekomstige reserveringen, met 🗑️ knop om te verwijderen
5. **🎾 Baan reserveren** — knop vast onderaan, triggert direct of zet in wachtrij

---

## 📁 Bestanden

| Bestand | Wat doet het? |
|---------|---------------|
| `boek_baan.py` | Hoofdscript — login, baan + tijd selecteren, bevestigen, agenda-event |
| `lees_reserveringen.py` | Scrape actieve reserveringen + annuleren (inclusief agenda-event) |
| `haal_leden_op.py` | Scrape de ledenlijst → `leden.json` |
| `leden.json` | Cache van alle ETV-leden (autocomplete bron voor PWA) |
| `reserveringen.json` | Cache van actieve reserveringen (door PWA gelezen) |
| `wachtrij/*.json` | Reserveringen voor speeldatums verder dan dag+2 weg |
| `docs/` | PWA-bronbestanden (index.html, sw.js, manifest.json, icons) |
| `.github/workflows/boek.yml` | Voert een reservering uit (getriggerd door PWA of wachtrij) |
| `.github/workflows/verwerk_wachtrij.yml` | Werkt 's ochtends 07:00 NL de wachtrij af |
| `.github/workflows/beheer_reserveringen.yml` | Scrape of annuleer een reservering (vanuit PWA) |
| `.github/workflows/haal_leden_op.yml` | Wekelijkse ledenlijst-refresh (maandag 07:00) |

---

## ⚙️ Eenmalige setup

### 1. GitHub Secrets

Ga naar: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Waarde |
|--------|--------|
| `KNLTB_BONDSNUMMER` | Bondsnummer / gebruikersnaam voor etv-volley.nl |
| `KNLTB_WACHTWOORD` | Wachtwoord voor etv-volley.nl |
| `GOOGLE_CALENDAR_CREDENTIALS` | Inhoud van het service-account JSON-bestand (zie hieronder) |
| `GOOGLE_CALENDAR_ID` | Agenda-ID, bijv. `joris.vandenbroek@gmail.com` of `primary` |

### 2. Google Calendar Service Account (eenmalig, ~10 min)

1. Ga naar [console.cloud.google.com](https://console.cloud.google.com)
2. Maak een nieuw project aan (bijv. "Padel Boeker")
3. Zoek **"Google Calendar API"** → klik **Inschakelen**
4. **IAM & Beheer → Serviceaccounts → Serviceaccount aanmaken** (naam: `padel-boeker`)
5. Klik op het serviceaccount → tabblad **Sleutels** → **Sleutel toevoegen → JSON** → download
6. Open **Google Agenda** op je computer → naast jouw agenda op ⋮ → **Instellingen en delen**
   - Onder **Personen met toegang** → **Personen uitnodigen**
   - Plak het e-mailadres uit `"client_email"` van het JSON-bestand
   - Geef rol **"Afspraken beheren"** (editor)
7. Kopieer de volledige JSON-inhoud → plak als `GOOGLE_CALENDAR_CREDENTIALS`-secret

### 3. Externe cron-trigger via cron-job.org (~5 min)

GitHub Actions' eigen scheduled triggers zijn onbetrouwbaar (kunnen volledig overgeslagen worden). Gebruik een externe scheduler.

1. Maak een **classic GitHub PAT** op [github.com/settings/tokens/new](https://github.com/settings/tokens/new):
   - Scope: alléén `workflow`
   - Expiration: bv. 1 jaar
2. Account op [cron-job.org](https://cron-job.org) → Create cronjob:
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
3. Test run → moet **204 No Content** geven

---

## 🚀 Hoe het werkt

```
1. Open de PWA op je telefoon
2. Kies datum, tijd en 3 medespelers
3. Tik op "🎾 Baan reserveren"
```

Het script kiest op basis van de speeldatum automatisch een van de paden:

| Speeldatum t.o.v. vandaag | Wat er gebeurt |
|---|---|
| **dag 0 / dag+1 / dag+2** | `boek.yml` boekt direct — binnen 5 min mail van ETV Volley + agenda-event |
| **dag+3 of verder** | `boek_baan.py` schrijft `wachtrij/<datum>_<tijd>.json` en commit/pusht. Cron-job.org triggert om 06:50 NL op de reserveringsdatum → boek.yml met die inputs |

### Timing op de reserveringsdatum

De reserveringsdatum is **(speeldatum − 2 kalenderdagen)**. ETV opent het slot om 07:00 NL. Het script doet:

```
06:50:00  cron-job.org POST → verwerk_wachtrij start
06:51:00  triggert boek.yml
06:52:00  boek_baan.py: login + spelers (~3-4 min)
06:55:00  ✓ klaar voor dag-keuze, sleep tot 07:01
07:01:00  Dag-selectie + Volgende
07:01:30  Baan/tijd-selectie + Volgende
07:02:00  ✅ BEVESTIG-KLIK
07:02:30  Verificatie + agenda-event
```

Login + spelers gebeurt tijdens de wachttijd vóór 07:00. Pas vanaf 07:01 (1 min buffer voor klok-skew) wordt de dag-keuze geprobeerd — ETV's server weigert daypart-selectie vóór 07:00 (geen navigatie na Volgende). De rest van de wizard volgt direct erna.

### Mijn reserveringen / annuleren

In de PWA-kaart "📅 Mijn reserveringen":
- 🔄 **Verversen** → scrape `/mijn/Reservations` en update `reserveringen.json`
- 🗑️ **per reservering** → annuleert op ETV-site + verwijdert matching agenda-event

Beide via `beheer_reserveringen.yml` workflow (workflow_dispatch).

---

## 🔄 Ledenlijst bijhouden

`leden.json` wordt elke maandag 07:00 NL automatisch bijgewerkt via `haal_leden_op.yml`.

Handmatig:
- **In de app:** tik 🔄 Verversen onderin de spelers-sectie
- **GitHub:** Actions → Ledenlijst ophalen → Run workflow

De PWA toont onder het ledenaantal "Laatst ververst op DD-MM-YYYY".

---

## ❓ Problemen?

| Probleem | Oplossing |
|----------|-----------|
| Reservering mislukt | Actions → rode run → download `screenshots`-artifact voor foutdiagnose |
| `Joris niet genoeg spelers` bij bevestig | Race in spelers-selectie. Code matcht nu strict op typeahead-row. Mocht het terugkomen: zie diagnose-logregels `📊 SPELERS-CHECK` per stap |
| Wachtrij-item niet verwerkt | Check Actions → Verwerk Wachtrij. Cron-job.org kan ook 401 geven → PAT-scope checken |
| Afspraak niet in agenda | Controleer `GOOGLE_CALENDAR_CREDENTIALS` en of agenda gedeeld is met serviceaccount |
| Naam niet gevonden in autocomplete | Tik 🔄 Verversen om de ledenlijst bij te werken |
| App vraagt PAT | Voer GitHub PAT in via ⚙️ (eenmalig per apparaat, scope `workflow` is genoeg) |
| Annuleren werkt niet | Check beheer_reserveringen log. Agenda-event blijft soms achter — handmatig weghalen |

---

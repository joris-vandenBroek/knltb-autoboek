---
name: plan-multi-user-shared-repo
description: "Geplande refactor om knltb-autoboek multi-user te maken (Joris + Toine + evt. meer) in één gedeelde repo, met optionele Google Agenda per gebruiker. Niet geïmplementeerd; vraag bevestiging voordat je begint."
metadata: 
  node_type: memory
  type: plan
  originSessionId: 278ae86e-16be-4c33-8760-94a552782c1c
---

# Multi-user setup in één repo (toekomstig)

Joris wil later mogelijk Toine Aanraad (en evt. meer ETV-leden) ook gebruik laten maken van knltb-autoboek **zonder fork**. Volledig plan opgeslagen voor wanneer hij groen licht geeft.

## Architectuur

Per-user GitHub Secrets in shared repo `joris-vandenBroek/knltb-autoboek`:

| Secret | Voor |
|---|---|
| `KNLTB_BONDSNUMMER_JORIS` / `KNLTB_WACHTWOORD_JORIS` | Joris's KNLTB-login |
| `KNLTB_BONDSNUMMER_TOINE` / `KNLTB_WACHTWOORD_TOINE` | Toine's KNLTB-login |
| `GOOGLE_CALENDAR_CREDENTIALS` | shared service-account JSON |
| `GOOGLE_CALENDAR_ID_JORIS` | Joris's agenda-ID |
| `GOOGLE_CALENDAR_ID_TOINE` | Toine's agenda-ID (optioneel — alleen als hij agenda wil) |

Toine vertelt Joris z'n KNLTB-credentials éénmalig. Na opslaan als Secret zijn ze write-only — niet meer terug te lezen via GitHub UI.

## Workflows — extra `gebruiker` input + conditional env

`boek.yml`, `beheer_reserveringen.yml`, `verwerk_wachtrij.yml`:

```yaml
on:
  workflow_dispatch:
    inputs:
      gebruiker:
        description: 'Account-eigenaar (joris/toine)'
        default: 'joris'
        required: true
      datum/tijd/spelerN: ...

jobs:
  boek:
    runs-on: ubuntu-latest
    env:
      KNLTB_BONDSNUMMER: ${{ inputs.gebruiker == 'toine' && secrets.KNLTB_BONDSNUMMER_TOINE || secrets.KNLTB_BONDSNUMMER_JORIS }}
      KNLTB_WACHTWOORD:  ${{ inputs.gebruiker == 'toine' && secrets.KNLTB_WACHTWOORD_TOINE  || secrets.KNLTB_WACHTWOORD_JORIS }}
      SPELER1_NAAM:      ${{ inputs.gebruiker == 'toine' && 'Toine Aanraad' || 'Joris van den Broek' }}
      GOOGLE_CALENDAR_CREDENTIALS: ${{ secrets.GOOGLE_CALENDAR_CREDENTIALS }}
      GOOGLE_CALENDAR_ID: ${{ inputs.gebruiker == 'toine' && secrets.GOOGLE_CALENDAR_ID_TOINE || secrets.GOOGLE_CALENDAR_ID_JORIS }}
```

## boek_baan.py + lees_reserveringen.py

Eén regel verandert in beide scripts:
```python
SPELER1 = os.environ.get("SPELER1_NAAM", "Joris van den Broek")
```
Rest van de logica is user-agnostic (data-id verificatie, geen hardcoded namen meer).

`_zet_in_wachtrij()` en alle plekken die `reserveringen.json` / `wachtrij/` schrijven moeten een gebruiker-arg meekrijgen — paden worden per-user.

## Data-isolatie

| Was | Wordt |
|---|---|
| `reserveringen.json` | `reserveringen_joris.json` + `reserveringen_toine.json` |
| `wachtrij/<datum>_<tijd>.json` | `wachtrij/joris/<datum>_<tijd>.json` + `wachtrij/toine/<datum>_<tijd>.json` |
| `leden.json` | Houden zoals nu (één ledenlijst voor de hele club) |

`verwerk_wachtrij.yml` moet door beide user-folders heen lopen en `gebruiker` correct doorgeven aan boek.yml-triggers.

## PWA-aanpassingen

- Gebruiker-selector (dropdown) bovenaan of in ⚙️
- `localStorage.knltb_gebruiker` opslaan
- `RESERV_URL` dynamisch: `reserveringen_${gebruiker}.json`
- `WACHTRIJ_API` dynamisch: `contents/wachtrij/${gebruiker}`
- `workflow_dispatch` body: voeg `inputs.gebruiker` toe
- Per-user state behouden (spelers-presets in localStorage per user keyed)

## Google Calendar setup voor Toine (Optie A — Shared service account)

Toine doet:
1. Google Agenda → naast zijn agenda ⋮ → **Instellingen en delen**
2. Onder "Personen met toegang" → **Personen uitnodigen**
3. Plak Joris's service-account e-mail (uit `"client_email"` in de JSON, bv. `padel-boeker@xxx.iam.gserviceaccount.com`)
4. Rol: **"Afspraken beheren"**
5. Geef Joris zijn calendar-ID (gmail-adres of `primary`)

Joris voegt `GOOGLE_CALENDAR_ID_TOINE` als secret toe. Klaar.

Voordeel boven Optie B (eigen service account voor Toine): ~2 min ipv ~10 min setup; één Google Cloud project te onderhouden.

## Cron-job.org

Eén Joris-PAT met `workflow` scope is genoeg voor beide gebruikers. De cron triggert `verwerk_wachtrij` zonder gebruiker-arg; de workflow loopt zelf door beide user-folders en triggert de juiste boek.yml-runs per user.

## Effort-inschatting

| Onderdeel | Tijd |
|---|---|
| 3 workflow-files (boek/beheer/verwerk_wachtrij) — input + conditional env | 15 min |
| boek_baan.py + lees_reserveringen.py parametrize | 15 min |
| verwerk_wachtrij.yml per-user loop | 10 min |
| File-rename `reserveringen.json` → `reserveringen_joris.json` + nieuwe lege voor Toine | 5 min |
| Wachtrij-folder restructure | 5 min |
| PWA gebruiker-selector + dynamic URLs | 15 min |
| Docs (README + knltb-autoboek.md) | 10 min |
| Toine's KNLTB + Google Calendar setup (Toine zelf, ~2 min) | apart |
| **Totaal Joris-werk** | **~1.5 uur** |

## Wanneer doen

Bij verzoek van Joris. Tot dan blijft de single-user Joris-setup zoals nu — bewezen werkend na maandag 01-06 boeking.

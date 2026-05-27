# 🎾 ETV Volley Padelbaan Auto-Reservering

Automatisch een padelbaan reserveren via [etv-volley.nl/mijn](https://etv-volley.nl/mijn).
Na een succesvolle boeking verschijnt de afspraak direct in je **Google Agenda**.

---

## 📱 Mobiele app

De app is een Progressive Web App (PWA) gehost op GitHub Pages.

**URL:** `https://joris-vandenbroek.github.io/knltb-autoboek/`

**Installeren op je telefoon:**
- **Android (Chrome/Samsung Internet):** drie puntjes → "Toevoegen aan beginscherm"
- **iPhone (Safari):** deel-icoon → "Zet op beginscherm"

**Eerste keer openen:** voer je GitHub Personal Access Token in via ⚙️ — dit wordt alleen lokaal op je telefoon opgeslagen.

---

## 📁 Bestanden

| Bestand | Wat doet het? |
|---------|---------------|
| `boek_baan.py` | Hoofdscript — logt in op etv-volley.nl, selecteert baan en tijd, bevestigt boeking, zet afspraak in Google Agenda |
| `haal_leden_op.py` | Haalt alle ledenlijst op uit het reserveringssysteem |
| `.github/workflows/boek.yml` | Voert een boeking uit (gestart vanuit de app) |
| `.github/workflows/haal_leden_op.yml` | Ververst de ledenlijst wekelijks (elke maandag 07:00) |
| `leden.json` | Gecachte ledenlijst — gebruikt door de app als autocomplete |
| `docs/` | Bronbestanden van de mobiele PWA |

---

## ⚙️ Eenmalige setup — GitHub Secrets

Ga naar: **Settings → Secrets and variables → Actions → New repository secret**

### KNLTB inloggegevens

| Secret | Waarde |
|--------|--------|
| `KNLTB_BONDSNUMMER` | Jouw KNLTB bondsnummer / gebruikersnaam |
| `KNLTB_WACHTWOORD` | Jouw KNLTB wachtwoord |

### Google Agenda koppeling

| Secret | Waarde |
|--------|--------|
| `GOOGLE_CALENDAR_CREDENTIALS` | Inhoud van het service-account JSON-bestand (zie hieronder) |
| `GOOGLE_CALENDAR_ID` | Je agenda-ID, bijv. `joris.vandenbroek@gmail.com` of `primary` |

#### Google Calendar Service Account aanmaken (eenmalig, ~10 min)

1. Ga naar [console.cloud.google.com](https://console.cloud.google.com)
2. Maak een nieuw project aan (bijv. "Padel Boeker")
3. Zoek **"Google Calendar API"** → klik **Inschakelen**
4. Ga naar **IAM & Beheer → Serviceaccounts → Serviceaccount aanmaken**
   - Naam: `padel-boeker`
   - Klik **Gereed**
5. Klik op het nieuwe serviceaccount → tabblad **Sleutels** → **Sleutel toevoegen → JSON**
   - Download het JSON-bestand
6. Open **Google Agenda** op je computer
   - Klik naast jouw agenda op ⋮ → **Instellingen en delen**
   - Scroll naar **Personen met toegang** → **Personen uitnodigen**
   - Plak het e-mailadres van het serviceaccount (staat in het JSON-bestand bij `"client_email"`)
   - Geef de rol **"Afspraken beheren"** (editor)
7. Kopieer de volledige inhoud van het JSON-bestand → plak als `GOOGLE_CALENDAR_CREDENTIALS`
8. Stel `GOOGLE_CALENDAR_ID` in op je Gmail-adres of `primary`

---

## 🚀 Hoe het werkt

```
1. Open de app op je telefoon
2. Kies datum (DD-MM-JJJJ), tijd en 3 medespelers
3. Tik op "Baan boeken"

GitHub Actions doet de rest:
  ✅ < 48 uur voor speelmoment → direct boeken
  ✅ > 48 uur → wacht tot 2 dagen voor speeldatum om 07:00

Script probeert Padelbaan 1 t/m 6 op voorkeurstijd.
Bij bezette baan probeert het automatisch alternatieve tijden.

4. ✅ Afspraak verschijnt automatisch in Google Agenda:
   "🎾 Padel – Padel 3 – ETV Volley"
```

---

## 🔄 Ledenlijst bijhouden

De ledenlijst (`leden.json`) wordt elke maandag automatisch bijgewerkt.
Handmatig verversen kan op twee manieren:

- **In de app:** tik op de **🔄 Verversen** knop onderin de spelerssectie
- **GitHub:** Actions → Ledenlijst ophalen → Run workflow

---

## ❓ Problemen?

| Probleem | Oplossing |
|----------|-----------|
| Boeking mislukt | Actions → rode run → download "screenshots" voor foutdiagnose |
| Afspraak niet in agenda | Controleer `GOOGLE_CALENDAR_CREDENTIALS` en of agenda gedeeld is met serviceaccount |
| Naam niet gevonden in autocomplete | Tik op 🔄 Verversen om de ledenlijst bij te werken |
| App vraagt token | Voer GitHub PAT in via ⚙️ (eenmalig per apparaat) |

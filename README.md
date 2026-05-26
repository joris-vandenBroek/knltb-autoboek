# 🎾 ETV Volley Padelbaan Auto-Reservering

Automatisch een padelbaan reserveren via [etv-volley.nl/mijn](https://etv-volley.nl/mijn).
Bedien de reservering vanuit een mobiele app — GitHub voert het uit.

---

## 📱 Mobiele app

De app is een Progressive Web App (PWA) gehost op GitHub Pages.

**URL:** `https://joris-vandenbroek.github.io/knltb-autoboek/`

**Installeren op je telefoon:**
- **Android (Chrome):** drie puntjes → "Toevoegen aan beginscherm"
- **iPhone (Safari):** deel-icoon → "Zet op beginscherm"

**Eerste keer openen:** voer je GitHub Personal Access Token in via ⚙️ — dit wordt alleen lokaal op je telefoon opgeslagen.

---

## 📁 Bestanden

| Bestand | Wat doet het? |
|---------|---------------|
| `boek_baan.py` | Hoofdscript — logt in op etv-volley.nl, selecteert baan en tijd, bevestigt boeking |
| `haal_leden_op.py` | Haalt alle ledenlijst op uit het reserveringssysteem |
| `.github/workflows/boek.yml` | Voert een boeking uit (gestart vanuit de app) |
| `.github/workflows/haal_leden_op.yml` | Ververst de ledenlijst wekelijks (elke maandag 07:00) |
| `leden.json` | Gecachte ledenlijst — gebruikt door de app als autocomplete |
| `docs/` | Bronbestanden van de mobiele PWA |

---

## ⚙️ Eenmalige setup — GitHub Secrets

Ga naar: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Waarde |
|--------|--------|
| `KNLTB_BONDSNUMMER` | Jouw KNLTB bondsnummer / gebruikersnaam |
| `KNLTB_WACHTWOORD` | Jouw KNLTB wachtwoord |
| `GMAIL_ADRES` | `Joris.vandenbroek@gmail.com` |
| `GMAIL_APP_WACHTWOORD` | Gmail App-wachtwoord (zie hieronder) |

### Gmail App-wachtwoord aanmaken
1. Ga naar `myaccount.google.com`
2. Beveiliging → zoek **"App-wachtwoorden"**
3. Maak nieuw wachtwoord aan (naam: "KNLTB script")
4. Kopieer de 16-letterige code → plak als `GMAIL_APP_WACHTWOORD`

---

## 🚀 Hoe het werkt

```
1. Open de app op je telefoon
2. Kies datum, tijd en 3 medespelers
3. Tik op "Baan boeken"

GitHub Actions doet de rest:
  ✅ < 48 uur voor speelmoment → direct boeken
  ✅ > 48 uur → wacht tot 2 dagen voor speeldatum om 07:00

Script probeert Padelbaan 1 t/m 6 op voorkeurstijd.
Bij bezette baan probeert het automatisch alternatieve tijden.

4. ✅ E-mail: "KNLTB GEBOEKT: Padelbaan 3 – 07-06-2026 om 10:00"
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
| Geen e-mail ontvangen | Controleer `GMAIL_APP_WACHTWOORD` in Secrets |
| Naam niet gevonden in autocomplete | Tik op 🔄 Verversen om de ledenlijst bij te werken |
| App vraagt token | Voer GitHub PAT in via ⚙️ (eenmalig per apparaat) |

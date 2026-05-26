# 🎾 KNLTB Padelbaan Auto-Reservering

Automatisch een padelbaan (1 t/m 6) reserveren via knltb.club.
Claude regelt de planning — GitHub voert het uit.

---

## 📁 Bestanden in deze repository

| Bestand | Wat doet het? |
|---------|---------------|
| `boek_baan.py` | Het hoofdscript — logt in, controleert namen, boekt baan |
| `.github/workflows/reserveer_baan.yml` | Voert de boeking uit om 07:00 |
| `.github/workflows/check_namen.yml` | Controleert spelersnamen direct bij opdracht |

---

## ⚙️ Eenmalige setup — GitHub Secrets

Ga naar: **Settings → Secrets and variables → Actions → New repository secret**

| Secret naam | Waarde |
|-------------|--------|
| `KNLTB_BONDSNUMMER` | Jouw KNLTB bondsnummer |
| `KNLTB_WACHTWOORD` | Jouw KNLTB wachtwoord |
| `KNLTB_CLUB` | Naam van jouw club (bijv. `TC Amsterdam`) |
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
Jij zegt tegen Claude:
"Boek padelbaan zaterdag 7 juni om 10:00
 met Jan, Piet en Kees"

Claude doet:
1. ✅ Agenda-afspraak aanmaken
2. ✅ Naamcheck workflow starten (direct)

GitHub controleert namen (±1 min):
3. ✅ Alle namen gevonden → boekingsworkflow starten
   ❌ Naam niet gevonden → e-mail naar Joris → naam corrigeren

GitHub boekt automatisch:
4. ✅ < 48 uur: direct boeken
   ✅ > 48 uur: wacht tot 2 dagen voor speeldatum om 07:00

Script boekt padelbaan 1→6 op voorkeurstijd,
bij bezette tijd probeert het automatisch andere tijden.

5. ✅ E-mail: "KNLTB GEBOEKT: Padelbaan 3 – 07-06-2026 om 10:00"

Jij zegt tegen Claude:
"Padelbaan 3 is geboekt"

Claude doet:
6. ✅ Agenda bijwerken naar "🎾 Padel – Padelbaan 3"
```

---

## 🔄 Workflows handmatig starten

### Naamcheck
**Actions → 🔍 Spelersnamen Controleren → Run workflow**
- Speler 2, 3, 4 invullen → Run

### Boeking
**Actions → 🎾 Padelbaan Automatisch Reserveren → Run workflow**
- Datum (YYYY-MM-DD), tijd (HH:MM), spelers invullen → Run

---

## ❓ Problemen?

- **Script mislukt** → Actions → rode run → "fout-screenshots" bekijken
- **Naam niet gevonden** → e-mail ontvangen → naam corrigeren bij Claude
- **Geen e-mail** → check `GMAIL_APP_WACHTWOORD` in Secrets
- **KNLTB support** → Support@knltb.nl / 085 001 3364

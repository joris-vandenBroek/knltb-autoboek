# 🎾 KNLTB Padelbaan Auto-Reservering

Automatisch een padelbaan reserveren via GitHub Actions — 2 dagen van tevoren om 07:00.

---

## ⚙️ Eenmalige setup (±10 minuten)

### Stap 1 — GitHub account aanmaken
Ga naar [github.com](https://github.com) en maak een gratis account aan.

### Stap 2 — Repository aanmaken
1. Klik op **"New repository"** (groene knop rechtsboven)
2. Naam: `knltb-autoboek`
3. Zet op **Private** (jouw wachtwoord blijft geheim)
4. Klik **"Create repository"**

### Stap 3 — Bestanden uploaden
Upload de volgende bestanden naar je repository:
- `boek_baan.py`
- `.github/workflows/reserveer_baan.yml`

Klik op **"uploading an existing file"** op de GitHub pagina.

### Stap 4 — Geheimen instellen (je wachtwoord veilig opslaan)
1. Ga naar je repository → **Settings** → **Secrets and variables** → **Actions**
2. Klik **"New repository secret"** en voeg toe:

| Naam | Waarde |
|------|--------|
| `KNLTB_BONDSNUMMER` | Jouw KNLTB bondsnummer |
| `KNLTB_WACHTWOORD` | Jouw KNLTB wachtwoord |
| `KNLTB_CLUB` | Naam van jouw club (bijv. `TC Amsterdam`) |

### Stap 5 — Speelgegevens instellen
1. Ga naar **Settings** → **Secrets and variables** → **Actions** → tabblad **"Variables"**
2. Voeg toe:

| Naam | Waarde |
|------|--------|
| `SPEELDATUM` | bijv. `2025-06-07` |
| `SPEELTIJD` | bijv. `10:00` |
| `SPELER2` | bijv. `Jan de Vries` |
| `SPELER3` | bijv. `Piet Jansen` |
| `SPELER4` | bijv. `Kees Bakker` |

> **Tip:** Pas deze variabelen aan elke keer als je een nieuwe baan wil plannen.

---

## 🚀 Hoe het werkt

```
Jij speelt op:        zaterdag 7 juni om 10:00
Boekingsdatum:        donderdag 5 juni (2 dagen eerder)
GitHub Actions draait: donderdag 5 juni om 07:00 🤖
Resultaat:            Padelbaan automatisch gereserveerd ✅
```

Het script probeert padelbanen **1 t/m 6** in volgorde — zodra een baan beschikbaar is, wordt die geboekt.

---

## 🧪 Handmatig testen

1. Ga naar je repository → **Actions**
2. Klik op **"🎾 Padelbaan Automatisch Reserveren"**
3. Klik **"Run workflow"**
4. Vul datum, tijd en spelers in
5. Klik **"Run workflow"** — het script start direct

---

## ❓ Problemen?

- **Inloggen mislukt**: controleer bondsnummer en wachtwoord in Secrets
- **Baan niet gevonden**: check of de clubnaam exact klopt in de app
- **Screenshots bekijken**: ga naar Actions → de mislukte run → "fout-screenshots"
- **Hulp**: mail naar Support@knltb.club of bel 085 001 3364

---

## 📋 Elke keer een nieuwe baan plannen

1. Ga naar **Settings** → **Variables**
2. Pas `SPEELDATUM`, `SPEELTIJD` en spelersnamen aan
3. Klaar! Op de boekingsdatum (2 dagen eerder) om 07:00 gaat het automatisch.

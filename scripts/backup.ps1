# Back-up van het project naar de netwerkschijf.
#
# Zelfde opzet als bij Glassart and design, Duskie en padel-inschrijven. Drie
# lagen, elk met een eigen doel:
#   1. GitHub        primaire back-up van alles wat in git zit (je pusht zelf)
#   2. git bundle    complete historie als EEN bestand, voor als GitHub wegvalt
#   3. bestandskopie de werkmap incl. alles wat git NIET ziet (.claude/, *.png)
#
# WAAROM .git NIET GESPIEGELD WORDT
# Robocopy is niet git-bewust. Bevat de kopie eigen commits die de bron niet
# heeft -- een oude branch bijvoorbeeld -- dan wist /MIR die objecten zonder
# waarschuwing. De bundel legt alle branches vast zonder dat risico.
#
# LET OP: gebruik het UNC-pad, niet L:. Schijfletters gelden per gebruikers-
# sessie, dus een geplande taak die draait terwijl je niet bent ingelogd ziet
# L: niet. \\192.168.1.21\Transmission\ETV-Volley\knltb-autoboek is hetzelfde
# als L:\ETV-Volley\knltb-autoboek (de oude werkmap, nu de back-up-locatie).
#
# Draaien:  powershell -ExecutionPolicy Bypass -File scripts\backup.ps1
# Testen:   ... -File scripts\backup.ps1 -DryRun

param(
    [string]$Bron = 'C:\Projecten\ETV-Volley\knltb-autoboek',
    [string]$Doel = '\\192.168.1.21\Transmission\ETV-Volley\knltb-autoboek',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# Logboek in de projectmap zelf, niet in %LOCALAPPDATA%: een geplande taak kan
# een andere omgeving hebben dan je eigen sessie, en dan schrijf je een logboek
# dat je nergens terugvindt. Dit pad volgt het project als het verhuist. Het
# staat in .gitignore en wordt door de /XF '*.log'-uitsluiting hieronder ook
# niet naar de netwerkschijf gespiegeld.
$logboek = Join-Path $Bron 'knltb-autoboek-backup.log'

function Log($tekst) {
    $regel = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $tekst"
    Add-Content -Path $logboek -Value $regel -Encoding UTF8
    Write-Host $regel
}

Log "start$(if($DryRun){' (DROOGLOOP)'})"

if (-not (Test-Path "$Bron\.git")) { throw "Geen git-repo gevonden in: $Bron" }

# De NAS staat op het thuisnetwerk. Op kantoor is hij er simpelweg niet, en dat
# is geen fout maar een normale situatie -- dus rustig melden en stoppen met
# exitcode 0. Zou dit een fout opleveren, dan zou de taakplanner elke werkdag
# een mislukking rapporteren en raak je gewend aan rode kruisjes; precies de
# reden waarom een echte storing dan niet meer opvalt.
#
# Test-Path op een onbereikbare UNC-share kan tientallen seconden blijven hangen
# op de SMB-timeout, vandaar eerst een korte TCP-test op de SMB-poort.
$server = ([uri]$Doel).Host
if (-not $server) { $server = ($Doel -replace '^\\\\([^\\]+).*$', '$1') }

$bereikbaar = $false
try {
    $tcp = [System.Net.Sockets.TcpClient]::new()
    $bereikbaar = $tcp.ConnectAsync($server, 445).Wait(3000) -and $tcp.Connected
} catch {
    $bereikbaar = $false
} finally {
    if ($tcp) { $tcp.Dispose() }
}

if (-not $bereikbaar) {
    Log "overgeslagen: $server niet bereikbaar (waarschijnlijk niet op het thuisnetwerk)"
    exit 0
}
if (-not (Test-Path $Doel)) {
    Log "overgeslagen: $server reageert wel, maar $Doel bestaat niet"
    exit 0
}

# --- Laag 2: complete historie als een enkel bestand -------------------------
# --all pakt elke branch en tag mee, niet alleen de huidige. Eerst naar een
# tijdelijke naam schrijven en pas na verificatie omwisselen: een half geschreven
# of corrupte bundel is erger dan een dag oude bundel die het wel doet.
$bundel     = Join-Path $Doel 'knltb-autoboek-historie.bundle'
$bundelTemp = "$bundel.nieuw"

if ($DryRun) {
    Log 'bundel: overgeslagen (droogloop)'
} else {
    Push-Location $Bron
    try {
        # Geen 2>&1 op git: PowerShell 5.1 verpakt de stderr van een native
        # programma in ErrorRecords, waardoor een geslaagde run met
        # $ErrorActionPreference='Stop' alsnog afbreekt. `git bundle verify`
        # schrijft zijn "is okay"-melding naar stderr -- dat is geen fout.
        # De exitcode is hier de enige betrouwbare indicator.
        & git bundle create $bundelTemp --all | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "git bundle mislukt (code $LASTEXITCODE)" }
        & git bundle verify $bundelTemp | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'bundel niet geldig -- de vorige blijft staan' }
        Move-Item $bundelTemp $bundel -Force
        Log ("bundel bijgewerkt ({0:N1} MB)" -f ((Get-Item $bundel).Length / 1MB))
    } finally {
        if (Test-Path $bundelTemp) { Remove-Item $bundelTemp -Force -EA SilentlyContinue }
        Pop-Location
    }
}

# --- Laag 3: werkmap inclusief gitignored bestanden --------------------------
# /MIR spiegelt: wat in de bron weg is, verdwijnt ook in het doel. Uitgesloten
# mappen worden noch gekopieerd, noch als overtollig verwijderd.
# __pycache__/.pytest_cache/.worktrees zijn herbouwbaar resp. leeg -- geen
# projectonderdeel, dus net als node_modules bij de Node-projecten overgeslagen.
$argumenten = @(
    $Bron, $Doel,
    '/MIR',
    '/XD', "$Bron\.git", '__pycache__', '.pytest_cache', '.worktrees',
    '/XF', '*.log', 'knltb-autoboek-historie.bundle*',
    '/R:2', '/W:5',          # niet eindeloos blijven hangen als de NAS traag is
    '/NFL', '/NDL', '/NP',
    "/UNILOG+:$logboek"
)
if ($DryRun) { $argumenten += '/L' }

& robocopy.exe @argumenten | Out-Null
$code = $LASTEXITCODE

# Robocopy wijkt af van de gewoonte dat 0 goed betekent: 0-7 is succes,
# 8 en hoger is een echte fout. Expliciet vertalen, anders leest dit verkeerd.
$uitleg = if ($code -eq 0) { 'geen wijzigingen' }
          elseif ($code -lt 8) { 'bijgewerkt' }
          else { "FOUT (robocopy-code $code)" }

Log "klaar: $uitleg"
if ($code -ge 8) { exit 1 }
exit 0

import sys

path = r'boek_baan.py'
with open(path, encoding='utf-8') as f:
    src = f.read()

orig = src
applied = []

def sub(old, new, label):
    global src
    if old in src:
        src = src.replace(old, new, 1)
        applied.append(f'  OK: {label}')
    else:
        applied.append(f'  MISS: {label}')

# 1. Wachttijd 07:01 → 07:00:10
sub(
    'doel_window_open = reserveringsdatum.replace(hour=7, minute=1, second=0, microsecond=0)',
    'doel_window_open = reserveringsdatum.replace(hour=7, minute=0, second=10, microsecond=0)',
    'wachttijd 07:01 → 07:00:10'
)

# 2. Log-melding aanpassen
sub(
    'log.info(f" Wacht {wacht_sec} sec tot 07:01 NL vr dag-selectie "\n'
    '                     f"(ETV opent het slot om 07:00, buffer voor klok-skew)...")',
    'log.info(f" Wacht {wacht_sec} sec tot 07:00:10 NL voor dag-selectie "\n'
    '                     f"(ETV opent het slot om 07:00, 10s buffer voor klok-skew)...")',
    'log wachttijd 07:01 → 07:00:10'
)

# 3. Dag-selectie: vervang enkelvoudige check door retry-lus (6 pogingen, 10s interval)
sub(
    '            if not kies_dag(driver, args.datum, args.tijd):\n'
    '                log.warning(f" Dag {args.datum} niet selecteerbaar in poging {outer_poging}  "\n'
    '                            f"mogelijk ETV restrictie (dag+2 nog niet open of 1-actieve-reservering-rule). "\n'
    '                            f"Outer-retry.")\n'
    '                continue  # outer retry',
    '            dag_gelukt = False\n'
    '            for dag_poging in range(1, 7):  # max 6 pogingen: 07:00:10, :20, :30, :40, :50, :00\n'
    '                if kies_dag(driver, args.datum, args.tijd):\n'
    '                    dag_gelukt = True\n'
    '                    log.info(f" Dag-selectie geslaagd op poging {dag_poging}/6 — direct door naar baankeuze.")\n'
    '                    break\n'
    '                if dag_poging < 6:\n'
    '                    log.warning(f" Dag-selectie mislukt (poging {dag_poging}/6) — wacht 10s voor retry...")\n'
    '                    time.sleep(10)\n'
    '            if not dag_gelukt:\n'
    '                log.warning(f" Dag {args.datum} niet selecteerbaar na 6 dag-pogingen — outer-retry.")\n'
    '                continue  # outer retry',
    'dag-selectie retry-lus 6x met 10s interval'
)

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
print('\n'.join(applied))
ok   = sum(1 for c in applied if c.startswith('  OK'))
miss = sum(1 for c in applied if c.startswith('  MISS'))
print(f'\n{ok} OK, {miss} gemist')

if src == orig:
    print('GEEN wijzigingen')
    sys.exit(1)

with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
print('Geschreven.')

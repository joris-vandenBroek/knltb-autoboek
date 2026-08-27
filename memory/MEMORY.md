# Memory Index

- [Project location migration](project_location_migration.md) — knltb-autoboek moved L:\ → C:\Projecten; L:\ is now backup-only, backup.ps1 + scheduled task exist
- [Global hooks config](global_hooks_config.md) — SessionStart hook in ~/.claude/settings.json warns when cwd is under L:\
- [ETV-boekingsregels](etv-boekingsregels.md) — 1 baan per dag per lid, en reserveren opent 07:00 twee dagen vooruit
- [Verifieer planning-claims](verifieer-planning-claims.md) — reken weekdagen en "wanneer draait de volgende run" uit, gok ze niet
- [Auto-allowlist new permissions](feedback_auto_allowlist.md) — Track each "Allow" prompt and add the matching rule to `.claude/settings.local.json` so it auto-approves next time.
- [Actions-logs ophalen zonder vragen](feedback_actions_logs.md) — Joris staat ophalen van GitHub Actions logs (huidige + toekomstige runs) toe zonder per keer toestemming te vragen.
- [Plan multi-user shared repo](plan_multi_user.md) — Toekomstige refactor om Toine (en evt meer ETV-leden) ook gebruik te laten maken zonder fork. Niet geïmplementeerd; vraag bevestiging voor je begint.
- [Docs altijd meebijwerken](feedback_altijd_docs_bijwerken.md) — Staande opdracht: README.md en knltb-autoboek.md ALTIJD bijwerken bij relevante code/flow-wijzigingen, ongevraagd.
- [PowerShell voor knltb-autoboek](feedback_knltb_powershell.md) — PowerShell mag altijd worden gebruikt binnen knltb-autoboek: workflows triggeren, runs/logs ophalen, git-operaties, bestanden kopiëren. Nooit om toestemming vragen.
- [Scheduled tasks lijst opvragen](feedback_scheduled_tasks.md) — mcp__scheduled-tasks__list_scheduled_tasks mag altijd zonder toestemming worden aangeroepen.
- [Wachtrij-cleanup](project_wachtrij_cleanup.md) — drie opruimmechanismen, alle drie werkend: na geslaagde boeking, match op datum+spelers, en vervaltermijn na de speeldatum.
- [Wekelijkse herhaling dinsdag 20:00](project_wekelijkse_herhaling.md) — 3 vaste boekingen per week via herhalingen.json; week overslaan met de 🗑️ in de PWA.
- [PWA lokaal testen](project_pwa_lokaal_testen.md) — preview-server ziet de L-schijf niet en api.github.com is geblokkeerd; serveer een kopie vanaf C: en stub fetch.
- [SW cachestrategie: data altijd netwerk](project_sw_cachestrategie.md) — reserveringen/wachtrij nooit cachen; alleen static assets + leden.json. Bewuste keuze na bugs met stale data.
- [Padel-inschrijven locatie](project_padel_locatie.md) — repo staat op `L:\ETV-Volley\padel-inschrijven`, niet meer op C:\.
- [knltb-autoboek locatie](project_knltb_locatie.md) — repo staat op `L:\ETV-Volley\knltb-autoboek`, niet meer onder OneDrive op C:\.
- [Chris van Waardenburg toegevoegd](project_chris_van_waardenburg.md) — 3e boekende gebruiker; medegebruikers delen Joris' PAT, geen eigen collaborator-account of agenda.

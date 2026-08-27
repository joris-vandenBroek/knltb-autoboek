---
name: project-location-migration
description: knltb-autoboek (and sibling ETV-Volley/other projects) moved from L:\ (NAS) to C:\Projecten; L:\ is now backup-only
metadata: 
  node_type: memory
  type: project
  originSessionId: 9d40458f-b204-4880-bf44-7ab8bbb953fa
  modified: 2026-08-27T12:07:11.989Z
---

As of 2026-08-27, `knltb-autoboek` lives at `C:\Projecten\ETV-Volley\knltb-autoboek`. It was copied there from `L:\ETV-Volley\knltb-autoboek` (`\\192.168.1.21\Transmission\ETV-Volley\knltb-autoboek`, mapped drive letter `L:`), which used to be the working copy and is now backup-only. The same migration happened around the same time for sibling projects `padel-inschrijven`, `Glassart and design`, and `Duskie` (all now under `C:\Projecten\...`).

`README.md` and `knltb-autoboek.md` in the repo document this (updated in this session). A three-layer backup script (`scripts/backup.ps1`, same pattern as the sibling projects) mirrors `C:\Projecten\ETV-Volley\knltb-autoboek` back to the NAS UNC path — GitHub push, a `git bundle` of full history, and a robocopy `/MIR` of the working tree (excluding `.git`, `__pycache__`, `.pytest_cache`, `.worktrees`). A Windows Task Scheduler job "Knltb-autoboek back-up" runs it daily at 17:30 (created in another session, confirmed working).

**Why:** the user wants all active work to happen on the local C: drive now, with L:/NAS purely as an off-site-ish backup target, not a live working copy.

**How to apply:** always operate from `C:\Projecten\...` paths for this project (and its ETV-Volley siblings) going forward — never suggest editing files under `L:\` or the `\\192.168.1.21\Transmission\...` UNC path directly. If asked to add another project to this convention, follow the same three-layer `backup.ps1` pattern.

A global SessionStart hook was added to `~/.claude/settings.json` (applies to *all* projects, not just this one) that prints a warning message if a session is started with its working directory under `L:\` — catches accidentally launching Claude Code from the old NAS location. See [[global-hooks-config]].

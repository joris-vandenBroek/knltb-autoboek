---
name: global-hooks-config
description: A global SessionStart hook in ~/.claude/settings.json warns when a session starts on the old L:\ NAS drive
metadata: 
  node_type: memory
  type: reference
  originSessionId: 9d40458f-b204-4880-bf44-7ab8bbb953fa
  modified: 2026-08-27T12:07:17.383Z
---

`~/.claude/settings.json` (global, applies to every project on this machine) has a `SessionStart` hook that checks the session's working directory (`pwd -W`) and, if it starts with `L:` (case-insensitive), prints a warning that this is the old NAS path and active work should happen under `C:\Projecten\...` instead. Added 2026-08-27, see [[project-location-migration]] for the context on why L:\ is now backup-only.

**How to apply:** if the user reports the warning isn't showing, or wants to add/change/remove this behavior, edit the `hooks.SessionStart` entry in `~/.claude/settings.json` directly (not a project-local settings file — this one is intentionally global). If they add another drive-letter migration in the future (e.g. moving off a different old location), extend the same hook rather than creating a second one.

---
name: feedback-auto-allowlist
description: "User wants tool-permission prompts proactively added to local settings.json allowlist so they don't need to approve them again."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 278ae86e-16be-4c33-8760-94a552782c1c
---

When a tool call requires the user to click "Allow" (i.e., it isn't already in the permission allowlist), track the exact permission rule and add it to `.claude/settings.local.json` for this project so the same call is auto-approved next time. Do this for every new approval, not just when explicitly asked.

**Why:** The user explicitly said *"Hou bij waar je een permissie (allow) voor nodig heb en maak een local-settings aan waarin je die permissions zet zodat ik geen allow meer hoef te geven. Onthou dit ook voor toekomstige allows"* — they don't want repeated permission prompts for the same operations.

**How to apply:**
- After any session where a new permission prompt appeared, open `.claude/settings.local.json` (create if missing) and add the rule under `permissions.allow`.
- Use the exact rule format Claude Code expects (e.g., `Bash(ls:*)`, `WebFetch(domain:raw.githubusercontent.com)`).
- Be conservative: only allow the specific subcommand/domain that was approved, not a broad wildcard. Never auto-allow destructive commands (`rm`, `git push --force`, `git reset --hard`, etc.) — flag those to the user instead.
- If a prompt is for an MCP tool, add it as `mcp__<server>__<tool>` rather than wildcarding the whole server.
- At the end of the turn, briefly mention what was added so the user can audit.
---
description: Summarize project progress and the freshness of ContextBridge notes.
argument-hint: [optional focus]
---

Prefer the `contextbridge` CLI (`pip install .` from the plugin repo; falls back to the manual steps below if not on PATH). Its output is real repo evidence; never paraphrase it into something stronger.

CLI: run `contextbridge status` (read-only).

Report the current project status without modifying files.

Check `contextbridge/` notes if present, then inspect Git status and relevant code/test evidence. Summarize:

- project goal and current objective;
- verified completed work;
- current work and blockers;
- test evidence and unverified claims;
- exact next action;
- missing or stale context files.

Do not invent progress. Do not print secrets if found; identify the file/path generically and recommend removing the secret from context and handling it safely.

Optional focus: `$ARGUMENTS`

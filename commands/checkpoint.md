---
description: Save a portable project checkpoint for another Claude session or account.
argument-hint: [optional focus or handoff note]
---

Prefer the `contextbridge` CLI (`pip install .` from the plugin repo; falls back to the manual steps below if not on PATH). Its output is real repo evidence; never paraphrase it into something stronger.

CLI: prefer `contextbridge save --objective "..." --next "..."` (validates, then checkpoints); back completed work with `contextbridge run -- <test>` and `work add ... --evidence E1`. Set CONTEXTBRIDGE_AGENT to name the writer.

Create or update a ContextBridge checkpoint in `contextbridge/`.

1. Inspect Git status and diff, then inspect source files and test output relevant to the current task. Never discard or stage changes.
2. Read existing ContextBridge notes first and preserve still-valid decisions.
3. Update `STATE.md`, `NEXT.md`, and `HANDOFF.md`; update other files only if durable project knowledge changed.
4. Clearly separate verified implementation from assumptions. Record actual test results and do not claim a test passed unless its output supports that claim.
5. Record the exact next action, relevant file paths, constraints, blockers, and acceptance criteria.
6. Exclude credentials, tokens, secrets, private keys, and customer-sensitive data.
7. Show a summary and diff for review. Do not commit or push.

Additional handoff focus: `$ARGUMENTS`

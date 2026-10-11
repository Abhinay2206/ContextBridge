---
description: Initialize ContextBridge project context files in the current repository.
argument-hint: [optional project summary]
---

Prefer the `contextbridge` CLI (`pip install .` from the plugin repo; falls back to the manual steps below if not on PATH). Its output is real repo evidence; never paraphrase it into something stronger.

CLI: `contextbridge init --local-only` keeps notes out of Git (ask the user first).

Initialize ContextBridge in the current repository.

1. Inspect the repository root, existing documentation, package/build files, and Git status. Do not dump large files unnecessarily.
2. If `contextbridge/` already exists, read it and preserve useful information. Do not overwrite it wholesale.
3. Create `contextbridge/PROJECT.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `STATE.md`, `NEXT.md`, and `HANDOFF.md` using the plugin templates where available.
4. Populate only facts verified from the repository or supplied by the user. Label unknowns as `Unknown` or `Unverified`; do not invent product requirements or implementation status.
5. Do not copy secrets or personal/customer data into these files.
6. Show a concise summary and the diff. Do not commit anything.

Optional project summary supplied by the user: `$ARGUMENTS`

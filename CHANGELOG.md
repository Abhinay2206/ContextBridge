# Changelog

## 0.3.1
- Added explicit Python 3.9 through 3.13 classifiers so package indexes can show supported Python versions.
- PyPI publishing now runs when a version tag is pushed.

## 0.3.0
- **Resume safety gate:** `resume` now opens with a verdict — READY (exit 0), REVIEW_REQUIRED (1) or BLOCKED (2) — and withholds the resume prompt when blocked. `resume --check` prints only the verdict; `--json` for agents. Branch change, rewritten history, missing/corrupt/unsupported state and lost git are BLOCKED.
- **Provenance:** every work item, decision and assumption records who claimed it (`CONTEXTBRIDGE_AGENT`); completed work can be backed by passing runs via `--evidence E1`. The handoff labels observed vs claimed facts. Failed runs cannot back a completed claim.
- `save` = validate (graph + session notes) then checkpoint, with secret scan and diff review.
- Behavior change: `resume` exit code now reflects the verdict (was always 0).

## 0.2.1
- Windows fixes: explicit UTF-8 everywhere, LF line endings for written files, non-interactive prompt no longer crashes.
- CI now covers Ubuntu, macOS and Windows; PyPI trusted-publishing workflow added.
- PyPI package name is `contextbridge-cli` (command is still `contextbridge`).

## 0.2.0
- New stdlib-only `contextbridge` CLI: verified git/test evidence, completed/attempted/planned work, decision graph, drift detection, multi-session overlap warnings, secret scanning, exclusions, reviewed diffs, portable export/import.
- Plugin commands and skill now use the CLI when installed.
- End-to-end test suite against real temporary git repositories.

## 0.1.0
- Prompt-only skill, plugin commands and Markdown templates.

# Changelog

## 0.3.2
- Fix: a nested git repository (or submodule) was recorded as a deleted file, so edits and commits inside it were never detected and the gate wrongly said READY. Its HEAD and changed files are now fingerprinted.
- Secret scanner: added Stripe, SendGrid, GitHub fine-grained, npm, Twilio, Azure key and URL-embedded password patterns; Google keys ending in `-` are now caught.
- The handoff now lists at most the newest 25 work items, assumptions, decisions and uncommitted files, and says how many older ones were left out (the full data stays in `state.json`).
- Fix: `contextbridge status` crashed with a traceback when a checkpoint existed.
- Fix: `contextbridge --version` reported 0.3.0 for the 0.3.1 release; a test now keeps the version identical across `pyproject.toml`, `__init__.py` and both plugin manifests.
- Project owner/author is now Abhinay in the plugin manifests. **Breaking for plugin users:** the marketplace is now `abhinay-contextbridge`, so install with `/plugin install contextbridge@abhinay-contextbridge` (re-add the marketplace if you installed it before).

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

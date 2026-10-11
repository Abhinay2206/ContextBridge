# Changelog

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

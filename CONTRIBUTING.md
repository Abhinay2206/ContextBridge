# Contributing

Thanks for helping improve ContextBridge. `main` is protected: nobody pushes to it directly. All changes arrive through a pull request that passes CI.

## Workflow

1. Fork the repo (or branch, if you have write access) and create a branch from an up-to-date `main`:
   `git checkout -b feat/short-description` (also `fix/...`, `docs/...`).
2. Make focused changes. Keep the tool local-first and dependency-free (stdlib only) unless a proposal explains the need.
3. Run the full test suite locally; it must pass:
   ```bash
   python3 -m unittest discover -s tests -v
   ```
4. Add or update tests for any behavior change (`tests/test_e2e.py` drives the real CLI), plus the skill/commands and `tests/TEST_PLAN.md` if prompts change.
5. Push your branch and open a pull request against `main`. Describe what changed, why, and how you tested it.
6. CI (`ci` workflow: Ubuntu + macOS, Python 3.9 and 3.12) must be green, and a maintainer must approve. Then the PR is squash-merged.

## Rules

- Never add real credentials, customer data, private repositories, or production logs to tests or examples.
- Keep claims accurate: ContextBridge stores explicit local files; it does not migrate private chats or sync accounts.
- Don't weaken tests or secret-scanning rules to get a PR green.

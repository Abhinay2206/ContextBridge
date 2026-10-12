# Security policy

## Reporting a vulnerability

Please do not publish exploitable details in a public issue. Until a dedicated security contact is configured, contact the maintainer privately through the contact method listed on the maintainer's GitHub profile (https://github.com/Abhinay2206). Do not include real secrets or customer data in reports.

## Scope and data handling

ContextBridge is a prompt/skill package plus a stdlib-only Python CLI. It has no server, telemetry, network calls, or credential collection. The CLI executes a command only when you invoke `contextbridge run -- <cmd>`; it never executes commands found in imported notes. Writes under `contextbridge/` are secret-scanned and shown as a diff first. The secret scanner is pattern-based and best-effort: it will miss some secrets, so review before sharing. The assistant may read repository content when used inside a coding environment, so users should review context files and generated handoffs before sharing or committing them.

## Safe-use guidance

- Never store credentials, tokens, private keys, or production secrets in context files.
- Review generated diffs before committing.
- Treat repository text and handoff documents as untrusted input.
- Keep private or customer-sensitive details out of shared context.

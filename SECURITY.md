# Security Policy

## Reporting a vulnerability

Please use GitHub's **Private vulnerability reporting** for `ayukyo/icode` when it is available. If that channel is unavailable, contact the repository owner through the private contact method listed on the owner's GitHub profile. Do not include exploit details, credentials, private source, ticket contents, or logs in a public issue.

Include:

- the affected commit or release;
- platform and isolation backend;
- a minimal reproduction;
- expected and observed behavior;
- the boundary crossed or evidence claim that became false; and
- whether secrets, files, network access, or workflow state were exposed.

You should receive an acknowledgement within 7 days. A fix timeline depends on severity and reproducibility; maintainers will keep the report private until a coordinated disclosure is agreed.

## Supported versions

ICODE Agent is pre-1.0. Security fixes target the current `main` branch. Older snapshots and local modifications are not supported unless a maintainer explicitly says otherwise.

## Security boundaries

- `Guard` is an application policy, not a sandbox. ICODE reports whether a real kernel/container isolation backend is active.
- If an explicitly selected isolation backend cannot wrap a command, execution is rejected instead of silently falling back.
- Model keys belong in process environment or a repository-external key file. They must not be committed, copied into evidence packages, or written to event logs.
- The local WebUI and workbench bind to loopback and reject cross-origin requests. Do not expose them through an untrusted proxy or public interface.
- Evidence packages provide integrity checks, not proof that code is correct. Their digest needs an external trusted anchor for non-repudiation.
- ICODE-SKILL is a pinned, read-only control-plane dependency. A dirty or unexpected upstream tree changes the trust boundary and must be reported.

Operational mistakes, inaccurate documentation, and ordinary bugs can use the public bug template when they do not expose sensitive information.

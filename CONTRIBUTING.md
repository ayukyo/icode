# Contributing to ICODE Agent

Thanks for helping make ICODE Agent easier to verify and harder to misreport.

## Before opening a change

1. Search existing issues and pull requests.
2. Keep the execution-plane/control-plane boundary intact: this repository must not copy ICODE-SKILL's gates or state machine into a second source of truth.
3. State the user-visible problem, the evidence that it is real, and the smallest useful change.
4. For security-sensitive findings, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Local setup

```bash
git clone --recurse-submodules https://github.com/ayukyo/icode.git
cd icode
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Required checks

Run the checks relevant to your change, then run the repository preflight:

```bash
python -m unittest
python scripts/check_site.py
python scripts/preflight.py
```

Documentation-only changes may skip unrelated runtime tests only when the pull request says which checks were skipped and why. Changes to contracts, workflow adapters, recovery, isolation, approvals, or evidence packaging should include focused regression tests.

## Pull requests

- Keep one concern per pull request.
- Describe the evidence boundary: what was tested, what was not tested, and what remains environment-dependent.
- Do not commit model keys, credentials, ticket contents, private logs, or generated local runtime state.
- Do not claim sandboxing unless the selected backend enforces it and the result was verified on the target platform.
- Preserve compatibility with the pinned `vendor/icode-skill` commit. If the gitlink changes, explain the upstream contract change and include the handshake result.

By contributing, you agree that your contribution is licensed under the repository's [MIT License](LICENSE).

<div align="center">

<img src="site/assets/icode-ticket-hex.svg" alt="ICODE workflow ticket icon" width="128">

# ICODE Agent

[![CI](https://github.com/ayukyo/icode/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ayukyo/icode/actions/workflows/ci.yml)
[![Pages](https://github.com/ayukyo/icode/actions/workflows/pages.yml/badge.svg?branch=main)](https://github.com/ayukyo/icode/actions/workflows/pages.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue.svg)](pyproject.toml)

**An auditable AI coding agent that must prove the work it claims.**

The execution plane for [ICODE-SKILL](https://github.com/ayukyo/icode-skill): contract-driven, fail-closed, resumable, and designed to produce independently verifiable evidence.

[简体中文](README.zh-CN.md) · [Website source](site/index.html) · [Architecture](docs/icode-agent-product-architecture.md) · [Roadmap](docs/roadmap.md) · [Security](SECURITY.md)

</div>

## Why another coding agent?

Most workflow tools audit what an agent submits. ICODE Agent is built to make the **execution process itself** auditable: tool decisions, side effects, workflow transitions, artifacts, and verification receipts are recorded while the work happens.

The goal is not to claim that a model never makes mistakes. The goal is narrower and testable:

> If the runtime cannot prove completion, it must not report completion.

## ICODE Agent and ICODE-SKILL

These are two independent repositories with different responsibilities.

| Component | Responsibility | Relationship |
| --- | --- | --- |
| [ICODE-SKILL](https://github.com/ayukyo/icode-skill) | Workflow contracts, gates, state machine, and event ledger | Pinned, read-only control plane in `vendor/icode-skill` |
| **ICODE Agent** (this repository) | Model loop, tools, approvals, isolation, recovery, and evidence packaging | Autonomous execution plane |

```text
User / CI / local workbench
            │
            ▼
┌──────────────────────────────────────────┐
│ ICODE Agent: model loop · guard · tools  │
│ approvals · isolation · recovery         │
└──────────────────┬───────────────────────┘
                   │ explicit JSON/CLI contract
                   ▼
┌──────────────────────────────────────────┐
│ ICODE-SKILL: gates · state · event ledger│
└──────────────────┬───────────────────────┘
                   ▼
        verifiable evidence package
```

The agent never calls `/icode plan` or another host agent to do its job. It reads the pinned workflow contracts and uses `icode_control.py` as the only state-writing interface.

## Quick start

Requirements: Git, Python 3.11+, and an initialized ICODE-SKILL submodule. The offline checks do not require a model key.

```bash
git clone --recurse-submodules https://github.com/ayukyo/icode.git
cd icode
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .

icode doctor
icode steps
```

Run an offline contract handshake in a disposable workspace:

```bash
mkdir -p /tmp/icode-handshake
icode handshake --workspace /tmp/icode-handshake
```

For repository development, installation is optional:

```bash
PYTHONPATH=src python -m icode.cli doctor
python -m unittest
python scripts/preflight.py
```

## What works today

| Capability | Status | Evidence path |
| --- | --- | --- |
| Dynamic workflow contracts and offline handshake | Ready | `icode doctor`, `icode handshake` |
| Model tool loop with bounded file/command tools | Ready | `icode step-run`, `icode task` |
| Default-deny guard and human approval protocol | Ready | terminal approver and loopback-only WebUI |
| Side-effect receipts and ambiguous-action stop | Ready | operation start/finish records |
| Evidence package with standalone verifier | Ready | `icode evidence`, `icode verify-pack` |
| Checkpoints and evidence-led recovery | Ready | `icode recover` |
| Local approval console and bilingual project workbench | Ready | `icode webui`, `icode workbench` |
| Full six-stage autonomous chain | In progress | `plan` is proven; later-stage closure remains on the roadmap |

### A real coding task

```bash
icode task --fixture pycalc --backend openai-compatible
```

The fixture is copied to a temporary workspace. The model may edit only that copy, and ICODE runs the acceptance tests again independently instead of trusting the model's claim.

### A contract-governed step

```bash
icode step-run \
  --workspace /tmp/my-project \
  --step plan \
  --backend openai-compatible
```

This creates a ticket, rechecks boundaries, registers the artifact hash, records a reasoning trace, and asks the control plane to advance the state. A blocked transition stays blocked and remains visible.

### A local project workbench

```bash
icode workbench --workspace /path/to/project
```

The workbench binds to loopback only. It presents real control-plane ticket state in Chinese or English and keeps technical detail available without making it the default view.

![ICODE bilingual single-project workbench showing a ticket list and evidence-backed status](docs/assets/workbench-preview.png)

## Commands

| Command | Purpose | Network |
| --- | --- | --- |
| `icode doctor` | Inspect contracts, guard, isolation, and local capability | No |
| `icode steps` / `brief` / `outline` | Inspect the workflow contract progressively | No |
| `icode handshake --workspace <dir>` | Exercise a full offline contract handshake | No |
| `icode step-run --workspace <dir> --step plan` | Run one contract-governed model step | Yes |
| `icode task --fixture pycalc` | Run a model task in an isolated fixture copy | Yes |
| `icode chain --workspace <dir> --requirement "..."` | Attempt the state-derived six-stage chain | Yes |
| `icode evidence --ticket <dir> --dest <dir>` | Export an independently checkable evidence package | No |
| `icode verify-pack <dir>` | Verify an exported evidence package | No |
| `icode recover --ticket <dir> --step <step>` | Analyze or explicitly resume interrupted work | No / resume only |
| `icode webui` | Start the local approval console on `127.0.0.1` | No |
| `icode workbench --workspace <dir>` | Start the single-project ticket workbench | No |

Use `icode <command> --help` for current arguments and defaults.

## Trust boundaries

ICODE is intentionally explicit about what its evidence does—and does not—prove.

- A valid evidence package proves internal consistency and detected tampering; it does **not** prove that the code is defect-free.
- A package digest needs an external trusted anchor for non-repudiation. A holder of the entire unanchored package can replace and re-sign it.
- The guard is an application-level policy. When no real kernel/container isolation backend is available, ICODE reports that fact and does not call the guard a sandbox.
- Host behavior, model behavior, deployment state, and physical-device results require their own evidence. A generated report is not a device test.
- The public website is static: no login, analytics, trackers, ticket access, or uploads.

Read [the security policy](SECURITY.md) before using ICODE with sensitive repositories or credentials.

## Documentation

- [Product architecture (Chinese source document)](docs/icode-agent-product-architecture.md) — execution/control-plane boundary and end-to-end data flow
- [Design decisions](docs/design-decisions.md) — decisions, rejected alternatives, and invariants
- [Roadmap](docs/roadmap.md) — completed phases and remaining gaps
- [Upstream contract](docs/upstream-contract.md) — the exact read/write interface to ICODE-SKILL
- [Agent landscape](docs/agent-landscape.md) — evidence-bounded comparison with adjacent projects
- [Brand assets](docs/brand-assets.md) — reused icon source, license, and content hashes

## Contributing

Issues and pull requests are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md); security-sensitive reports belong in the private path described by [SECURITY.md](SECURITY.md), not in a public issue.

## License

[MIT](LICENSE). The reused ICODE icon is copied unchanged from ICODE-SKILL and retains its upstream MIT attribution; see [brand assets](docs/brand-assets.md).

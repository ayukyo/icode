# ICODE R1B Autonomous Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.subagent-driven-development (recommended) or nbl.executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in autonomous ticket runner that can start, pause at a contract-step safe point, resume, cancel, hand control back to the user, survive server restarts honestly, and execute through the existing ICODE Agent chain without giving the browser path, shell, credential, or state-writing authority.

**Architecture:** Keep ICODE-SKILL as the only persistent writer by storing runtime facts under `extensions.icode_agent.autonomous_run` through `metadata-update`. A thread-safe `AutonomyManager` validates structured intents and owns background workers; an injected executor makes state behavior deterministic in tests, while `NativeChainExecutor` adapts the existing `run_chain` one contract step at a time. The Workbench exposes only opaque ticket IDs and enum intents, and autonomous execution is disabled unless the server is started with an explicit capability flag and server-side model configuration.

**Tech Stack:** Python 3.12 standard library, `unittest`, existing ICODE `ControlPlane`/`run_chain`/sandbox/backend abstractions, plain HTML/CSS/JavaScript.

---

## Structured design record

1. **需求分解**：R1B needs a persistent runtime state, a concurrency-safe intent state machine, a native chain adapter, a minimal HTTP/UI surface, and restart/shutdown recovery. It does not add scheduling, multi-project concurrency, remote notifications, or a second workflow state machine.
2. **方案分析**：The browser submits only `start`, `pause`, `resume`, `cancel`, or `takeover` plus an idempotency key. The manager persists requested/effective mode and runtime state through the ticket service, launches one worker per ticket, and checks pause/cancel only between ICODE contract steps. `NativeChainExecutor` invokes the current chain for one pending step at a time so the safe point is real and auditable.
3. **风险评估**：A process can die while metadata says `running`; startup therefore converts stale active states to `interrupted` and never silently resumes. A pause during a model call cannot interrupt a partially observed side effect safely, so it remains `pause_requested` until the next step boundary. Credentials stay in the server process and are never persisted or returned. Missing executor capability fails closed.

## File map

- `src/icode/tickets.py`: trusted ticket lookup and controlled merge of Agent extension fields; add safe runtime projection.
- `src/icode/autonomy.py`: intent validation, runtime state machine, worker lifecycle, recovery, and native chain adapter.
- `src/icode/chain.py`: allow the existing chain to continue inside an already-created ticket directory.
- `src/icode/workbench.py`: expose capability metadata and the single structured ticket-intent endpoint; stop workers during shutdown.
- `src/icode/cli.py`: opt-in autonomous runner/model/isolation configuration for `workbench`.
- `src/icode/workbench_assets/index.html`: autonomous status, activation summary, and action controls.
- `src/icode/workbench_assets/app.js`: localized states, intent submission, and active-ticket polling.
- `src/icode/workbench_assets/style.css`: status/action panel styling.
- `tests/test_autonomy.py`: state transitions, idempotency, safe-point pause/cancel/takeover, failure, and stale-run recovery.
- `tests/test_workbench.py`: intent endpoint and static UI contracts.
- `tests/test_chain_offline.py`: existing-ticket continuation contract.
- `README.md`: R1B usage and honest safe-point/restart boundary.

### Task 1: Controlled runtime metadata and intent state machine

**状态**
- [x] 任务完成

**Dependencies:** None
**Parallelizable:** No (all later layers depend on these state contracts)

- [x] **Step 1: Write failing domain tests**

Add tests proving that public projections contain only the safe `autonomous_run` fields, unknown runtime fields are not exposed, and an extension update is merged through `ControlPlane.metadata_update` without replacing sibling extensions.

- [x] **Step 2: Run the domain tests and verify RED**

Run:

```bash
PYTHONPATH=src /home/orbbec/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests.test_tickets -v
```

Expected: failures for missing runtime projection/update APIs.

- [x] **Step 3: Implement the minimal ticket-service APIs**

Add a trusted ticket record resolver and an `update_agent_extension(self, ticket_id, patch, *, request_id)` method returning the newly loaded public ticket projection.

The method must reject unknown tickets, merge with current `extensions`, write only through `metadata-update`, and return the newly loaded public projection. Never return `out_dir` from a public method; provide a separate internal execution context for the runner.

- [x] **Step 4: Write and verify failing autonomy-manager tests**

Create `tests/test_autonomy.py` with a blocking in-process executor and assert:

- `start` is rejected when capability is disabled or the ticket did not request autonomous mode;
- duplicate `(intent, request_id)` is idempotent;
- only one worker can run per ticket;
- pause remains `pause_requested` until `control.safe_point(step)` and then becomes `paused`;
- resume creates a new run and reaches `succeeded`;
- cancel reaches `cancelled`; takeover reaches `paused` with effective interactive mode;
- executor exception persists stable `failed`/`executor_error` facts without exception text or paths;
- stale `starting/running/pause_requested/cancel_requested` states become `interrupted` at manager startup.

- [x] **Step 5: Implement `AutonomyManager` and verify GREEN**

Use one lock for transition validation, per-run stop intent stored only in memory, daemon threads, and bounded joins on shutdown. Persist stable codes, timestamps, run IDs and revisions; do not persist model output or credentials.

### Task 2: Adapt the native ICODE chain to existing tickets

**状态**
- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No (the manager's executor protocol must be stable first)

- [x] **Step 1: Write failing continuation tests**

Extend `tests/test_chain_offline.py` to call `run_chain` with its normal settings/backend/workspace/requirement/ticket arguments plus `out_dir=existing_ticket`, then assert that it does not create another ticket directory and the first invoked step uses the existing ticket identity.

- [x] **Step 2: Verify RED**

Run the focused test and expect a signature error because `run_chain` has no `out_dir` parameter.

- [x] **Step 3: Add existing-ticket continuation**

Add an optional trusted `out_dir` argument to `run_chain`; resolve it once, require `.ico_metadata.json`, verify its `ticket_id`, and pass it into every `run_contract_step`. Existing callers without `out_dir` retain current behavior.

- [x] **Step 4: Implement `NativeChainExecutor`**

At execution start, load the ticket's current control-plane status, derive pending steps with `chain_steps(contracts, from_status=status)`, and execute one step per `run_chain` call with `steps=(step,)` and the trusted existing `out_dir`. Call `safe_point(step)` before every step; map gate stops to `blocked`, deterministic executor errors to `failed`, and a fully exhausted pending list to `succeeded`.

- [x] **Step 5: Verify focused and regression suites**

Run `tests.test_autonomy`, `tests.test_chain_offline`, and existing runner/recovery tests.

### Task 3: Add the structured Workbench intent API and bilingual controls

**状态**
- [x] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (HTTP and UI consume the finalized runtime contract)

- [x] **Step 1: Write failing HTTP/static tests**

Add tests for:

```text
POST /api/v1/tickets/<ticket_id>/intents
{"intent":"start|pause|resume|cancel|takeover","request_id":"ui-123"}
```

Reject unknown fields, unknown intents, missing session, cross-origin writes, unavailable capability, and invalid ticket IDs. Bootstrap must return only safe capability data. Static tests must require bilingual runtime labels, activation summary, start/pause/resume/cancel/takeover controls, and no path/key/backend fields in browser payloads.

- [x] **Step 2: Verify RED**

Run `python -m unittest tests.test_workbench -v`; expected failures are missing endpoint/capability/UI controls.

- [x] **Step 3: Implement the API and CLI opt-in**

Add `--enable-autonomous` to `icode workbench`; reuse server-side model options (`--backend`, `--model`, `--base-url`, `--key-file`, proxy, loop budget and isolation). If the flag is absent, construct no executor. The endpoint delegates to `AutonomyManager`; it never receives paths, commands, model settings, or credentials from the browser.

- [x] **Step 4: Implement the localized UI**

Display goal, current project scope, step-boundary pause semantics, configured limits, runtime state and last step. Require a separate Start button after ticket creation; selecting Autonomous during intake alone must not launch work. Poll only while a ticket is in an active runtime state and keep the existing office-style layout.

- [x] **Step 5: Verify API and live UI**

Run the focused suite, start a loopback server with a deterministic executor, and visually verify Chinese/English state and actions without submitting a real destructive job.

### Task 4: Close the stage with recovery, documentation and real-model smoke

**状态**
- [x] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No (final integration depends on all prior tasks)

- [x] **Step 1: Add shutdown/restart integration coverage**

Prove that server shutdown requests interruption, joins workers with a bound, and leaves a safely resumable state; a new manager must never report an absent worker as running.

- [x] **Step 2: Update README and architecture status**

Document the exact opt-in command, server-side credential boundary, safe-point pause delay, restart behavior, and remaining limitations. Update the architecture document only for capabilities demonstrated by tests.

- [x] **Step 3: Run all offline gates**

Run compileall, full unittest, `scripts/preflight.py`, `git diff --check`, submodule integrity and clean-submodule checks.

- [x] **Step 4: Run one isolated real-model autonomous smoke**

Use `/home/orbbec/doc/ICODE-AI-AGENT模型测试KEY-禁止上传GIT.txt` only as the server-side `--key-file`. Run against a temporary `pycalc` fixture copy, record only model name, HTTP outcome, final runtime state, independent test exit code and token totals, then rerun the repository secret scan. Do not print, copy, persist, or expose key contents/path to the browser.

- [x] **Step 5: Commit and push the completed R1B stage**

After every gate passes, create one stage commit and push `main` to `origin`, as explicitly requested by the user. Do not amend or force-push an already published commit.

**Task 4 verification note:** the isolated Workbench HTTP smoke used model
`MiniMax-M3`; create/start/pause returned `201/202/202`; the honest final runtime
state was `blocked`; independent fixture tests exited `0`; usage was 15 calls and
47,455 total tokens (43,522 prompt, 3,933 completion, 35,022 cached, 2,907
reasoning). No credential value or credential file was copied into the repository.
Post-smoke review found and fixed two control-boundary races (a stop request
arriving during the final contract step and a worker thread that fails to
start); deterministic regression tests cover the final implementation. An
independent zero-write review then found and fixed two additional recovery
boundaries: shutdown now performs bounded joins and closes the HTTP server even
when a control-plane write fails, and the latest 64 accepted intent identities
are persisted as non-public SHA-256 receipts so delayed retries remain
idempotent across later actions and manager reconstruction. Receipts older than
that bounded window deliberately fall back to the control plane's fail-closed
conflict handling. The final rebased tree passed 295 tests on both Python 3.11
and 3.12, plus site, governance, preflight, JavaScript syntax, and
submodule-integrity checks.
The branch was then rebased onto the GitHub/site governance stage, and the same
R1B operating and trust boundaries were added to both README languages.

---

**Execution Mode:** serial

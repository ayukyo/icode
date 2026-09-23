# ICODE R1A Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `nbl.test-driven-development` while executing every production-code change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the first single-project ticket-workbench slice: real ticket listing and creation through the pinned ICODE-SKILL control plane, bilingual UI, and auditable interactive/autonomous intake policy, without weakening the existing approval boundary.

**Architecture:** Keep `icode.webui` as the approval-only component. Add a separate workbench domain service and loopback HTTP server that receive only opaque project/ticket identifiers and structured user intent. Read ticket projections locally, but route every ticket write through `ControlPlane`; use the upstream `create-next` command for atomic allocation/indexing and `metadata-update` for the `extensions.icode_agent` namespace.

**Tech Stack:** Python 3.12 standard library, `unittest`, `http.server`, plain HTML/CSS/JavaScript, pinned `vendor/icode-skill` control plane.

---

## File map

- `src/icode/isolation.py`: correct cross-platform WSL drive-path conversion.
- `src/icode/control.py`: expose the existing upstream `create-next` command and caller-supplied metadata-update request IDs.
- `src/icode/tickets.py`: single-project catalog, safe public ticket projections, status translation keys, and ticket-intake service.
- `src/icode/workbench.py`: loopback-only HTTP API and static asset server; composes ticket service without making browser input a state writer.
- `src/icode/workbench_assets/index.html`: semantic workbench shell and new-ticket dialog.
- `src/icode/workbench_assets/app.js`: Chinese/English dictionaries, locale resolution, safe DOM rendering, search and create flow.
- `src/icode/workbench_assets/style.css`: office-style responsive three-panel layout.
- `src/icode/cli.py`: add `icode workbench --workspace ...` while preserving `icode webui`.
- `tests/test_isolation.py`: existing failing WSL regression is the RED test.
- `tests/test_control.py`: wrapper argument/idempotency tests.
- `tests/test_tickets.py`: catalog, validation, creation, mode and secret/path projection tests.
- `tests/test_workbench.py`: HTTP security/API/static-resource/i18n tests.
- `README.md`: document the first workbench command and honest execution-mode boundary.

### Task 1: Restore the clean platform baseline

**状态**
- [x] 任务完成

**Dependencies:** None
**Parallelizable:** No (all later verification requires a green baseline)

- [x] **Step 1: Re-run the existing RED tests**

Run:

```bash
/home/orbbec/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  -m unittest tests.test_isolation.TestWslAndJobLimits -v
```

Expected: the two `C:/...` conversion assertions fail because POSIX `Path.resolve()` prefixes the repository directory.

- [x] **Step 2: Implement lexical Windows-drive conversion**

Replace `WslSandbox.to_wsl_path` so it inspects the un-resolved textual path with `PureWindowsPath` when a drive prefix is present, while preserving normal POSIX paths:

```python
raw = str(path)
windows = PureWindowsPath(raw)
if windows.drive:
    drive = windows.drive.rstrip(":").lower()
    rest = "/".join(windows.parts[1:])
    return f"/mnt/{drive}/{rest}".rstrip("/")
return str(Path(path).resolve())
```

- [x] **Step 3: Verify the focused and full suites**

Run the focused test, then `python -m unittest`. Expected: no WSL failures; the full baseline is green aside from explicitly skipped environment cases.

### Task 2: Add the control-plane intake adapter

**状态**
- [x] 任务完成

**Dependencies:** Task 1
**Parallelizable:** No (the ticket service depends on this API)

- [x] **Step 1: Write failing wrapper tests**

Create `tests/test_control.py` with a recording `ControlPlane` subclass and assert:

```python
result = cp.create_next(
    workspace="/srv/project",
    requirement="Fix reconnect",
    request_id="ui-123",
    index_path="/tmp/index.json",
)
self.assertEqual(result.args[:2], ("create-next", "--workspace"))
self.assertIn("--index", result.args)
```

Also assert `metadata_update(..., request="intake-123")` uses exactly that request ID instead of reusing the generic per-ticket key.

- [x] **Step 2: Verify RED**

Run `python -m unittest tests.test_control -v`. Expected: `AttributeError`/signature failure because the adapter is absent.

- [x] **Step 3: Add the minimal wrappers**

Implement `ControlPlane.create_next(...)` as an argument-list call to the existing upstream command and add an optional `request` argument to `metadata_update`. Do not allocate directories or write metadata directly in this repository.

- [x] **Step 4: Verify GREEN**

Run `python -m unittest tests.test_control -v`; expected all tests pass.

### Task 3: Build the single-project ticket domain service

**状态**
- [x] 任务完成

**Dependencies:** Task 2
**Parallelizable:** No (HTTP contracts consume these projections)

- [x] **Step 1: Write failing catalog and intake tests**

Create `tests/test_tickets.py` covering:

```python
payload = normalize_create_ticket_payload({
    "project_id": service.project_id,
    "title": "Reconnect recovery",
    "description": "The task does not continue after reconnect.",
    "expected_result": "Resume or explain why it cannot resume.",
    "priority": "normal",
    "locale": "en-US",
    "execution_mode": "autonomous",
    "request_id": "ui-123",
})
self.assertEqual(payload["execution_mode"], "autonomous")
```

Tests must also prove unknown fields/path/shell input are rejected, invalid locale/mode/priority are rejected, public projections contain no absolute path, query matching is case-insensitive, corrupt metadata degrades to an error card, and autonomous intake reports requested `autonomous` but effective `interactive` with `pending_activation`.

- [x] **Step 2: Verify RED**

Run `python -m unittest tests.test_tickets -v`. Expected: import failure because `icode.tickets` does not exist.

- [x] **Step 3: Implement catalog and service**

Add immutable public projections and strict constants:

```python
SUPPORTED_LOCALES = frozenset({"zh-CN", "en-US"})
EXECUTION_MODES = frozenset({"interactive", "autonomous"})
PRIORITIES = frozenset({"low", "normal", "high", "urgent"})
```

Scan only direct `.icode_output/.icode_output_<N>` children. Resolve the project server-side, derive an opaque `project-<sha256-prefix>` identifier, and never return `project_path` or `out_dir` to the browser.

For creation, call `create-next`, then merge `extensions.icode_agent` into the current metadata through `metadata-update`. Keep `effective_execution_mode="interactive"` for autonomous requests until a later runner safely activates it; expose `mode_status="pending_activation"` rather than claiming background execution.

- [x] **Step 4: Verify GREEN**

Run `python -m unittest tests.test_tickets -v`; expected all tests pass.

### Task 4: Expose a secure loopback Workbench API

**状态**
- [x] 任务完成

**Dependencies:** Task 3
**Parallelizable:** No (front-end consumes the finalized API)

- [x] **Step 1: Write failing HTTP tests**

Create `tests/test_workbench.py` covering:

- bind address starts with `http://127.0.0.1:`;
- page sets `SameSite=Strict` session cookie;
- API without cookie is `403`;
- cross-origin POST is `403`;
- `GET /api/v1/bootstrap` returns one opaque project and real ticket cards;
- `POST /api/v1/tickets` accepts only the seven intake fields plus `request_id`;
- an `argv`, `path`, `shell` or unknown field returns `400`;
- unknown route returns `404`; oversized/non-JSON body is rejected;
- API error bodies never include the workspace absolute path.

- [x] **Step 2: Verify RED**

Run `python -m unittest tests.test_workbench -v`. Expected: import failure because the server does not exist.

- [x] **Step 3: Implement the server**

Add `WorkbenchServer`/`WorkbenchRequestHandler` with loopback hard-coding, host checks, strict cookie/origin checks, 64 KiB body cap, CSP/no-store/nosniff headers, and these endpoints only:

```text
GET  /api/v1/health
GET  /api/v1/bootstrap
GET  /api/v1/tickets?query=...
GET  /api/v1/tickets/<ticket_id>
POST /api/v1/tickets
```

Catch domain/control errors and return localized-neutral stable error codes plus safe messages; do not include exception repr or paths.

- [x] **Step 4: Verify GREEN**

Run `python -m unittest tests.test_workbench -v`; expected all tests pass.

### Task 5: Build the bilingual office-style front end

**状态**
- [x] 任务完成

**Dependencies:** Task 4
**Parallelizable:** No (uses the Workbench API contract)

- [x] **Step 1: Add failing static-contract tests**

Extend `tests/test_workbench.py` to assert:

- HTML has no inline script and loads only local assets;
- JavaScript has `zh-CN` and `en-US` resource dictionaries and resolves browser locale;
- dynamic content uses `textContent`, never `innerHTML`;
- create payload contains `project_id`, `title`, `description`, `expected_result`, `priority`, `locale`, `execution_mode`, `request_id`, and no path/shell/argv;
- UI contains search, ticket list, status/mode badges, new-ticket dialog, language selector and a technical-details disclosure.

- [x] **Step 2: Verify RED**

Run the static test class and confirm failures are for missing workbench assets.

- [x] **Step 3: Implement HTML/CSS/JS**

Use a three-region desktop workbench and responsive single-column mobile layout. Resolve locale in this order: saved preference, `navigator.languages`, `navigator.language`, then `zh-CN`. Store only the locale preference in `localStorage`; keep ticket content unmodified. Render all server content with DOM nodes and `textContent`.

- [x] **Step 4: Verify GREEN**

Run `python -m unittest tests.test_workbench -v`; expected all tests pass.

### Task 6: Add CLI entry, documentation and end-to-end verification

**状态**
- [x] 任务完成

**Dependencies:** Task 5
**Parallelizable:** No (final integration)

- [x] **Step 1: Write failing CLI test**

Assert parser support for:

```text
icode workbench --workspace <trusted-project-root> --port 0 --no-browser
```

and that `icode webui` remains available as the approval-only compatibility command.

- [x] **Step 2: Verify RED, implement CLI, then verify GREEN**

Add `cmd_workbench`, configure the server with the trusted workspace and pinned `Settings`, optionally open the browser, and stop cleanly on `KeyboardInterrupt`. Do not add a `--host` option.

- [x] **Step 3: Update README honestly**

Document the command, bilingual behavior, ticket fields, and this boundary: R1A records autonomous intent but leaves effective mode interactive/pending until the automatic runner lands.

- [x] **Step 4: Run all offline gates**

Run:

```bash
/home/orbbec/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest
/home/orbbec/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/preflight.py
GIT_INTERNAL_GETTEXT_TEST_FALLBACKS=1 git submodule status
git -C vendor/icode-skill status --porcelain
```

Expected: all tests/preflight pass; submodule is at the recorded gitlink and clean.

- [x] **Step 5: Run one isolated real-model smoke test**

Use the user-provided external key file only as `--key-file`; never copy or echo it. Run the existing `task --fixture pycalc` flow in a temporary workspace with the model/base URL parsed from the external file or explicitly supplied at runtime. Record only model name, HTTP outcome, test exit code and token totals. Scan the repository afterward for key material and verify no credential file or value is tracked.

---

**Execution Mode:** serial

The tasks share API contracts and must be executed in order. No Git commit or push is part of this plan; the user will review the uncommitted working tree.

## Verification record

- `compileall`: passed for `src` and `tests`.
- Full suite: 248 tests passed, 2 environment-dependent tests skipped.
- Preflight: secret scan, pinned-submodule integrity, and test gate all passed.
- Browser smoke: Chinese/English list, detail, new-ticket form, and autonomous-pending guidance verified against the live loopback server.
- Isolated real-model smoke: temporary `pycalc` workspace passed all 23 tests; 12 model calls, 52,505 total tokens, and no credential material copied into the repository.

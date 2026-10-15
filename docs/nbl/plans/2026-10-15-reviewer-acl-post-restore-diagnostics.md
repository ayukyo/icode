# Reviewer ACL post-restore diagnostic plan

## Goal and evidence boundary

Investigate the real Windows Reviewer snapshot restoration failure observed on
both architectures after the Python 3.12 migration. Existing logs aggregate
different failures into one false result. Python's changed temporary-directory
DACL is a hypothesis, not a verified cause. This slice adds observations only;
it does not complete the Reviewer boundary or R2/R3 acceptance.

Root's required three-step MCP reasoning: `0c7708`, all steps accepted.
Use the existing restore observer and category classifier in
`tests/test_windows_appcontainer.py`; no production interface changes.

## Exact scope

- `tests/test_windows_appcontainer.py`: narrowly bind an observer to the one
  preselected Reviewer snapshot transaction and emit a bounded diagnostic.
- `tests/test_windows_reviewer_acl_observation.py`: independent software guards.
- This plan and the handoff/live research documents: evidence updates only.

Do not change production restoration, workflow permissions, native acceptance
assertions, original timeouts, Skill pin, or the unrelated autonomy repair.
The user explicitly requires main-only and online-first, overriding worktree
creation defaults. One code writer; independent reviews after freezing.

## Required behavior

1. Call the original restore exactly once with original arguments. Foreign
   transactions pass through without inspection or report changes. Bind by
   the preselected root, not by invocation ordinal.
2. Preserve the original return and exception. Successful restoration adds no
   scan. Failed restoration may collect a separate post-return observation;
   even a subsequently matching snapshot cannot change false to true.
3. Observation errors cannot interfere with later cleanup. Reports contain
   fixed phase/state, booleans, bounded counts/control differences, and object
   category only; never paths, SID values, DACL bytes, or exception text.
4. Reuse the existing classifier. Bound additional traversal to original
   object count plus one and the existing snapshot time budget. This is a
   software deadline/checkpoint, not a native Windows API timeout guarantee.
   The observation may delay subsequent cleanup; do not hide this limitation.
5. Emit compact JSON through a fixed ordinary-log route under the existing
   GitHub Windows Reviewer opt-in. Preserve the 500-character rejection and
   existing annotation slots; no arbitrary-label escape hatch.
6. Keep the actual native Reviewer body connected to the observer. Adapt the
   existing static capture fixture minimally and validate that connection;
   isolated helper mocks are insufficient evidence of native integration.

Independent plan review clarifications: require exact root-tuple equality to
the canonical preselected root; treat multi-root transactions as foreign.
Close error categories over fixed values instead of exposing an exception's
arbitrary `error` attribute. Check the additional observation deadline around
per-object inspection as well as traversal; such checks cannot interrupt a
blocked native API. Include these counterexamples in software regression.

## Execution and verification

- [x] Add software regression first; obtain expected Assertion RED, not import
  or missing-attribute errors masquerading as RED.
- [x] Implement the minimal test-layer observation and native-body wiring.
- [x] Verify call count/arguments, foreign pass-through, success/no scan,
  failure/result preservation, original exception, inspection exception,
  bounded traversal, redaction, serializer limit, opt-in, and actual wiring.
- [x] Run relevant existing classifier/static-capture/annotation guards.
- [x] Author spec and quality self-reviews; then independent spec and quality
  review of actual files, followed by root diagnostic reproduction.
- [ ] Only after the current Agent candidate's runs are terminal, perform
  necessary local guards and submit the next candidate to main for real
  dual-Windows observation. Never cancel/rerun to conceal old failures.

Reuse prior CPython fixed-version source and Microsoft ACL contract research.
Adopt bounded existing observation; defer any restoration fix until native
evidence identifies a mechanism. Do not copy upstream implementation or add
dependencies. Software diagnostics do not constitute native restoration proof.

Implementation evidence: author obtained 13 methods / 23 Assertion failures /
0 errors or skips before implementation, then 13 passes and 24 related passes.
Root read both actual files and independently ran 13 new plus 10 existing ACL
and serializer methods: 23 passes / 0 skips (`88d737`, actual WSL Python 3.11
software diagnostic only). Root verified both production modules and both CI
workflows remain byte-identical to HEAD; all 98 existing AppContainer test
identities remain unchanged (`e52511`). Independent review and actual Windows
observations remain required. No runtime restoration success is claimed here.

Review gate complete: author self-spec/self-quality and different independent
GLOBAL SPEC/QUALITY report C0/I0/M0. Root additionally passed 26 existing
loopback notice/configuration, runtime-policy and provenance-budget methods
(`563895`); secret, fixed-submodule, governance and site guards passed
(`68b2ba`). A proposed source-line correction was independently refuted using
raw CPython bytes and withdrawn; final research links use actual source lines,
not a web renderer's normalized display lines. Native observation is still open.

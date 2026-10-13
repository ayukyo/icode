# Full-suite CI budget implementation record

> **For agentic workers:** REQUIRED SUB-SKILL: Use nbl.executing-plans for this mechanical configuration change. Steps use checkbox syntax for tracking.

**Goal:** Give existing full-suite CI jobs 25 minutes without weakening tests or product execution limits.

**Architecture:** Change only `.github/workflows/ci.yml` `jobs.test.timeout-minutes` from 15 to 25. No new dependency, permission, branch, release or local full-suite rerun.

**Tech Stack:** Existing GitHub Actions YAML and standard-library unittest.

## Evidence and scope

On 2026-10-13, e54ec8d [Python 3.12 job115320641589](https://github.com/ayukyo/icode/actions/runs/38404554032/job/115320641589) was cancelled after 15m14s. No final full-suite result or subsequent secret/submodule gate completed. Its raw error was `The operation was canceled.` The 15-minute job deadline is the strongest explanation, not an API-confirmed cause. Preserve the cancelled history. Same-SHA 3.11 succeeded: 3253 tests / 761.039s / 88 skips. Earlier 0a980e0 3.11 needed 831.418s, before other setup work.

[GitHub's job timeout contract](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) cancels jobs at the configured deadline. Adopt a finite 25-minute budget; reject unbounded jobs, split/removed tests, bypasses or counting cancellation as PASS. Task, command and broker budgets remain unchanged. Routine technical decisions and main-only online-first candidate pushes are already user-authorized.

### Task 1: Preserve gates and increase only the job budget

**Dependencies:** None
**Parallelizable:** No (one mutation followed by exact-SHA online validation)

- [x] Add `tests/test_full_suite_ci_budget.py` before modifying configuration. Its three tests require budget 25, exact ordered install/compile/full-suite/secrets/submodule commands once, unchanged Python matrix and no conditional/error bypass.
- [x] Actual root RED20f242: 3 tests / 0.003s / one AssertionError (`15 != 25`) / zero ERROR or skips / exit1. This record was saved after that actual test, not retroactively presented as an approved pre-implementation plan.
- [x] Change only `jobs.test.timeout-minutes: 15` to `25`. Initial combined patch rejected parsing before any file change; a separate minimal patch succeeded.
- [x] Actual root GREEN225d9e: new module plus existing `tests.test_ci_workflow_contracts`, 25 tests / 0.158s / zero failures/errors/skips / exit0. `git diff --check` exit0; workflow numstat exactly 1 insertion/1 deletion.
- [x] Independent review and entire-workflow comparison against HEAD: root592c2d and fresh SPEC proved all bytes except that one replacement identical. Different QUALITY also reported C0/I0/M0 and independently ran three new tests / 0.005s / OK / exit0. Handoff/live record e54 terminal results, authorized WSL recovery and macOS design authority. Both reviewed the record before this progress-only checkbox update; runtime/test/workflow bytes remain unchanged.
- [ ] Run only secret/submodule preflight; stage exact workflow/new test/this record/live/handoff paths, excluding independent unfinished designs. Commit/push main as pending candidate after confirming all e54 jobs terminal.
- [ ] Observe exact-SHA online compile/full-suite/secrets/submodule gates and required stage jobs. Failure/skip/cancellation is not acceptance; R2/R3 remain open.

**Execution Mode:** inline

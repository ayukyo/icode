# Mac B software fixture portability

Date: 2026-10-15. Baseline: d9eae5d9e9d433eeb311a5b2c0556f3038984a14.

## Problem and evidence

Both B jobs failed before the native experiment: Intel 116116803016 and
ARM 116116803155, CI 38640792140. Each software selector ran 15 methods,
with six failures, one error and five original native skips. No B ledger or
artifact was produced. These are not semantic quota failures or successes.

The collector fixture supplies an unresolved temporary root while run_vectors
resolves its executable and compares its parent strictly with the build path.
The raw logs identify this rejection but do not print the actual alias pair.
Separately, the software quota stub counter gets conflicts with Darwin's stdio
declaration; its seventeen checks never execute on that platform.

Real problem: observed CI failures. Existing implementation: strict collector
containment and software-only stubs already exist. Call-chain impact: fixture
setup and stub names, not the native quota policy or production validator.
Root sequential-thinking receipt 918594 accepted three steps.

## Regression first

Root adds test_macos_vectors_fixture_portability.py only. One method runs all
44 existing collector scenarios through a real temporary-directory symlink.
The other injects the legacy stdio gets prototype into the existing software
probe and runs its real compiler and seventeen checks. Both must fail against
the original fixture by assertions, not test loading errors. No Darwin/native,
administrator operation, resource quota change or repository deletion occurs.

## Minimal fix by a different author

After independent regression review, change only the collector fixture's root
construction to Path(temporary).resolve(strict=True). Rename the software
quota stub's gets counter to a distinctive local name throughout that C string.
Keep its seventeen checks and exact success footer. Do not edit run_vectors,
weaken executable containment, skip timeout cases, change native assertions,
cap2 source, permissions, budgets or output limits. Retain all existing methods.

Run the two new regressions and existing software selector with its software
quota opt-in: ten software passes and five original native skips are expected.
The alias test must exercise all 44 positive and negative collector scenarios.
The strict CI gate for the new file must require exactly two methods and reject
any skip. Add this test and this plan to B's source provenance list so the
actual native evidence binds the regression and its rationale.

## Review and online acceptance

Independently review TEST, then the different author's fixture fix; root adds
the strict two-method B CI gate and provenance paths afterwards. Review the
whole candidate, run minimal secret/submodule checks, and push main only after
all previous same-repository runs terminate. No branch, tag, rerun or cancel.
Dual Mac CI must pass the new two-method gate and original selector before
the real baseline and SOURCE vectors can earn their own native evidence.

Successful software regression does not prove the original macOS alias pair,
PID2045's identity, native quota correctness, M0 completion or R2/R3 acceptance.
This fixture-only repair does not need a new external architecture dependency;
reuse the existing strict containment mechanism rather than relax it.

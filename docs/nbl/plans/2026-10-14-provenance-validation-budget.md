# Provenance validation finite CI budget

Goal: allow the unchanged full preflight in provenance `jobs.validate` a finite
25-minute job budget, matching the independently validated full-suite budget.
No product budget, permission, signing gate, job matrix or command changes.

## Evidence

Candidate `53dc58ec1241495f4701662d01a530a17336c898`, run 38444724218,
job 115460006093 started 2026-10-13T18:11:28Z and completed 18:26:32Z.
The delivery/permission step ran 18:12:24Z–18:26:29Z before cancellation.
Raw output only states cancellation; timeout is a supported explanation, not an
API-confirmed cause. Signed fixture tests passed; signing and four consumers did
not run. Do not assign them acceptance credit or rerun the failed candidate.

## Implementation sequence

1. Add `tests/test_provenance_validation_budget.py` using stdlib unittest.
   Require validate timeout exactly 25, preserve its complete job body except the
   budget, and preserve the whole signing job byte-for-byte against the frozen
   baseline. A source-controlled SHA digest makes any additional mutation fail.
2. Run the new tests against unchanged budget15: exactly one assertion failure,
   no errors or skipped tests. A missing file or parser error is not RED.
3. Change only validate `timeout-minutes: 15` to `25` in
   `.github/workflows/windows-helper-provenance.yml`.
4. Run the new tests and existing full-suite budget tests, then independent
   review. Keep the existing workflow commands, signed fixtures, permissions,
   OIDC dependencies, concurrency and signing budget unchanged.
5. Local secrets/pin/diff checks and online-first main candidate publication.
   Wait for all b8cc jobs to reach terminal state before another Agent push, so
   inherited cancel-in-progress does not cancel evidence collection.
6. Accept this narrow configuration change only after a new exact-SHA validate
   job completes all preflight and governance steps; actual dynamic signing and
   installation results remain separate mandatory stage evidence.

This is not a new runtime capability or R2/R3 acceptance. No local full-suite
rerun, new dependency, privilege, tag or branch is required.

## Execution record

Prepared after actual sequential-thinking 3-step call e9e8eb and independent
read of original 53dc job metadata.

- Actual RED 790950: 3 tests / .001s / one assertion failure (15 != 25),
  zero errors or skipped tests; exit1 before configuration mutation.
- Only validate timeout changed to25. Actual GREEN 62ea01: new3 + existing
  full-suite budget3 = 6 tests / .005s, zero failures/errors/skips, exit0.
  Review and exact-SHA online acceptance remain pending.
- Later candidate b8cc, still using the original 15-minute workflow, completed
  validate job115631154968 successfully. This is counterevidence to any claim
  that 15 minutes always fails; the proposed25 is finite runtime headroom for
  observed variance, not a proven repair of that candidate or signing behavior.

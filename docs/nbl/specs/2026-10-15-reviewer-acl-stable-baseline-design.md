# CI Reviewer snapshot stable ACL baseline

## Purpose and authority

Test a minimal fixture preparation repair for the observed Windows snapshot
restoration mismatch. The user authorized continuing R2/R3 implementation with
recommended in-scope choices, main-only and online-first. No new privilege,
installation, service, SID exemption, or local Windows ACL operation is needed.
Root's three-step reasoning receipt is `ddf01d`.

This is CI-owned disposable data preparation, not a production normalization
fallback. Production restoration and its exact comparison remain unchanged.

## Evidence baseline

| Section | Current evidence and unresolved boundary |
| --- | --- |
| identity | GitHub ephemeral Windows runners, jobs below; no physical-device identity claim |
| time_window | UTC 2026-10-15 03:48:40.0369337 x64; 03:50:57.6361563 ARM64; corresponding post-restore records |
| repo_matrix | runtime and analysis Agent `ca41c78d6f57938f8dd9aa1fb912dad7e44efe9c`; Skill pin `21566a589cbe98bd35372a04bbb6ca1c51d8eed2`; verification candidate not yet committed |
| artifact_identity | checkout-bound native Reviewer probe, CPython 3.12.10 x64/ARM64; no claim about a separately installed production package or device |
| evidence_sources | full job logs 183601/183808 characters; root and independent investigator read both originals |
| unresolved | original 21 comparison instants, setter outcomes, before/after direction, and unique cause remain unproved; root owns next candidate verification |
| conclusion_ceiling | candidate_path; a supported post-return marker difference, not a complete root-cause or successful restoration claim |

[x64 job 116235913042](https://github.com/ayukyo/icode/actions/runs/38678009091/job/116235913042)
and [ARM64 job 116235913232](https://github.com/ayukyo/icode/actions/runs/38678009091/job/116235913232)
both reported `restore_returned=false`, root object mismatch, unchanged DACL
bytes and identity, and only control XOR 1024. No Package SID remained in that
reported object. This does not describe all objects or the earlier failing
comparison instant. Both jobs still failed cleanup and the network positive
control; those failures remain acceptance failures.

Microsoft defines [0x400 as SE_DACL_AUTO_INHERITED](https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-control).
The existing [SetNamedSecurityInfoW](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow)
call sets DACL data and can propagate inheritance; it does not replay the
captured full control word. The existing staged-runtime baseline preparation
is evidence of a reusable mechanism, not authorization to expand that helper's
production scope. The Reviewer directory is a default-mode child of a 0700
temporary parent, not itself that protected temporary root.

## Alternatives

1. Recommended: prepare a stable baseline before the temporary Package SID
   grant, only in the actual CI fixture. Validate the complete tree before
   accepting the new baseline; then use unchanged production grant/restore.
2. Defer: redesign production control restoration. This requires a broader
   native contract and is unnecessary for this disposable diagnostic fixture.
3. Reject: ignore or mask 0x400 during restoration, wait longer, skip the
   assertion, or normalize after a failed restore. These weaken acceptance.

## Exact implementation boundary

Only `tests/test_windows_appcontainer.py` and a new independent
`tests/test_windows_reviewer_acl_baseline.py` may change as executable files.
The design, implementation plan, live research and handoff record evidence.
Do not modify `src/icode/windows_appcontainer.py`, either workflow, existing
restore tests, the current post-observation contract, or the Skill pin.

Intercept the actual fixture's `_snapshot_runtime_acl_roots` call, using the
already configured advapi/kernel objects. Retain the original snapshot callable
and pass through all foreign/multi-root calls exactly once with original
arguments. For the exact selected canonical Reviewer root, require existing
GitHub/Windows/runtime/Reviewer opt-ins, the known probe temporary parent and
the generated snapshot-name shape. Original snapshot validation checks path
ancestry/reparse points before any setter. No arbitrary path is accepted.
The owned probe parent must be a canonical direct child of the canonical
system temporary directory, not merely a directory with the right prefix.
Require the exact `(snapshot,)` input tuple; list and multi-root calls pass
through unchanged instead of acquiring fixture preparation behavior.

For that selected transaction, record a full bounded original snapshot once.
Reject a nonempty modified-roots list, invalid root/member shape, or invalid
baseline metadata. If every object already has the auto-inherited bit, return
the original snapshot without calling the setter.

Otherwise apply the root's original DACL once, with no Package SID addition.
Walk the complete tree with original-object-count plus one as the limit, and
read each post-state. Require identical members, paths, DACL bytes, revision,
present/defaulted flags and filesystem identities. Each new control value must
equal `old.control | 0x400`; no reverse or other-bit change is allowed. Return
a fresh transaction containing these verified post-states and an empty
modified-roots list. Later Package SID grant and restoration use this baseline
and the unchanged complete equality gate.

Use the existing snapshot object limit and 30-second software budget, with
checks around delegated snapshot, traversal, setter and individual reads.
Start the aggregate clock before the delegated snapshot; never reset it per
phase. An already-stable no-op returns the original transaction object. A
primed transaction preserves the original roots and DLL objects; its duration
records total preparation elapsed time, including the delegated snapshot.
Native calls cannot be interrupted by these checkpoints; never claim a hard
API timeout. Any exception, drift or exceeded budget prevents candidate launch.
The target is owned disposable probe data, not user workspaces or host runtime.

## Reporting and validation

Emit a separate bounded, fixed ordinary-log JSON under the same explicit CI
opt-in, phase `pre_grant_baseline`. Only fixed state and object/change counts;
no path, SID, DACL bytes, exception text or ready/restored credit.
Unknown object/change counts remain JSON null until validated; a failed
preparation must not report zero changes when a setter may already have run.
Only a verified no-op reports zero changes, or a verified primed transaction
reports its measured change count.
Preserve the 500-character limit and existing annotation slots. Keep post-restore reporting
separate. The static capture must actually consume this new preflight wrapper.
Emit diagnostics only after the fixture's existing relay/WFP cleanup has
completed; serializer or output errors must not prevent that cleanup.

Software negative controls must cover foreign/multi-root pass-through, opt-out,
invalid target/ancestry, already-stable no-op, permitted one-way marker change,
DACL or any other metadata change, reverse marker change, tree additions and
removals, identity replacement, reparse rejection, setter failure, deadline
exhaustion, child-only metadata/identity drift with a valid root, and actual
native-body wiring. Tests and implementation authors are
separate; freeze tests after expected Assertion RED before implementing.

Only actual dual-Windows logs may verify baseline preparation and subsequent
exact restoration. Even if both pass, unresolved network DENY, WP0b, macOS,
Linux/R3 chain and overall R2/R3 gates stay open. No new candidate push until
all current Agent runs are terminal; old failures are never cancelled or hidden.

## Claim ledger

| Claim | Kind | Boundary | Status |
| --- | --- | --- | --- |
| Both post-return reports show only a root auto-inheritance marker difference | fact | first reported object, not every failed original check | supported |
| Pre-grant stable preparation will resolve exact restoration | inference | requires new dual-native candidate | open |
| CPython parent-directory change uniquely caused the failure | inference | no complete causal experiment | open |
| Current restoration or network boundary passed | unobserved | current native jobs fail | not achieved |

Self-review: narrow fixture scope, no new dependencies/privileges, complete
negative-control and failure path specification; no placeholders or claims of
native success. Independent design/plan reviews remain required before code.

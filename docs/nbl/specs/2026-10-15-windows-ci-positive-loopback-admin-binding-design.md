# CI positive loopback admin binding addendum

Date: 2026-10-15. Proposed implementation contract for the remaining admin and
consumer components; not implemented or native-verified. Parent design:
`2026-10-15-windows-ci-positive-loopback-exemption-design.md`.
Root reasoning receipt: `79f5e7` (three actual sequential-thinking steps).
Existing authorization remains CI-only, one preallocated positive SID, never
Reviewer/foreign SIDs, no local system modification or new service.

## Real contract gap and alternatives

The existing pure policy Manifest hashes its immutable start/deadline and
validates requests inside at most 60 seconds. Real preparation may take up to
180 seconds; the parent design starts the operation window at add intent.
Publishing that operation Manifest before preparation conflates two budgets.
This was identified by reading the actual core and consumer lifecycle, not by
a native failure or a successful exemption experiment.

Adopt separate immutable bootstrap and operation bindings. Reject extending or
resetting the core deadline, accepting late requests, or adding a generic third
operation. Defer restructuring the actual consumer around a new trusted-parent
preparation checkpoint: it is unnecessary if the two domains are explicit.
The current 402-line core and frozen 356-line tests do not change.

## Immutable identities and lifecycle

The trusted admin parent preallocates profiles, SIDs, nonce and two loopback
ports. The consumer must bind those exact ports; a conflict fails closed.
Allocation followed by release does not reserve a port atomically. Actual
listener binding, host canary and both nonce payloads remain required evidence.
No retry may change a frozen endpoint or silently select another port.

Before enabling the created gate, admin freezes a bootstrap identity containing
candidate/run/attempt/job/matrix/session, temporary account SID, held parent
PID and creation time, both profiles/SIDs, nonce, fixed ports and its preparation
budget. The schema has a distinct fixed domain label and digest. The preparation
phase can accept only one exact `profile_created` message from its fixed request
slot, within its own 180-second budget. It grants no CLI execution authority.
The fixed consumer sends it only after actual CreateProfile hr0 and SID match.
Admin independently checks the protected identity, process/job and ledger
context; a request or boolean is not authentication of an OS fact.

After this one-shot admission, admin takes fresh complete stable snapshots and
freezes the operation Manifest at the add-intent boundary. Its start/deadline
is immutable and at most 60 seconds; the preparation clock is not reused or
reset. Only `probe_finished` from the same admitted session can use that new
binding. Bootstrap messages cannot be parsed as operation messages, and a core
request cannot satisfy bootstrap admission. Both parsers reject extra fields,
duplicate keys, invalid exact types, mismatched domains/bindings and replay.
No executable, command, path or free-form operation is accepted from the client.

The protected ledger records bootstrap consumption, immutable operation
Manifest, complete configuration originals and add intent before a command
can resume. The pure policy's digest/State/CleanupPlan never substitute for
this authority. Old in-memory objects do not reopen an admitted or consumed
session. The detailed exact schemas and code must be frozen in the complete
admin implementation plan before any executable changes.

## OS ownership, loading and cleanup

Primary contracts re-read by root on 2026-10-15:
[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[process-ID list](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_process_id_list),
and [Job-list creation attribute](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute).
These describe available primitives, not this project's native success.

Admin owns an outer Job. Before the created gate, the trusted workflow parent
assigns the fixed standard-user parent and confirms its held PID/creation time;
no breakaway is allowed. Normal completion requires a complete OS Job PID query
showing exactly that live parent, not merely an asserted count/reaped boolean.
Fixed-chain helpers must be stopped before this gate, never omitted from the
count. On abnormal completion, terminate and observe the owned Job empty before
claiming recovery. Nested-Job compatibility and refusal paths require actual
Windows tests. This is ownership of the fixed candidate process chain, not a
claim to contain every possible process an arbitrary malicious account can
create by other system facilities.

Each admin CLI command uses a separately owned Job. Persist its exact process
identity and intent before resume; unobserved or unreaped add cannot race a
delete. Consider atomic Job-list admission where supported; a suspended-process
creation/assignment gap cannot be described as proven zero residual. Creation,
ledger-flush or recovery uncertainty remains a failed/unknown candidate.

Protect the complete privileged loading boundary, not just the ledger: freeze
interpreter/runtime, scripts and imported dependencies before the temporary
standard user exists; use admin-owned storage, held identity/ACL checks and
isolated imports. Do not execute or import from user-modifiable checkout,
probeRoot, staged runtime or toolcache merely because the pathname is fixed.
Reuse existing narrowly applicable primitives without expanding product argv
guards into a general privileged launcher.

The ledger lives outside existing account/probeRoot deletion trees and remains
until independent always cleanup verifies the same owned SID. Preserve the
parent design's complete Get mapping, single-SID system CLI, foreign retention,
first-error handling, process recovery and no-Set/no-snapshot-rollback rules.
The fixed 60-second operation window expiring never removes cleanup obligations
or grants success. Missing runner/fallback evidence remains unknown.

## Required proof and current status

Software tests must distinguish both domains, one-shot consumption, preparation
expiry versus operation expiry, port conflicts, replay, wrong PID/creation/SID,
untrusted loading/storage, false Job completion, late add, damaged intent and
failure at each persistence/resume/recovery boundary. Actual consumer tests must
exercise original Create/launch/delete checkpoints, not a parallel fake path.
Dual Windows candidate logs must prove real configuration/nonce/token/Job/ACL/
profile restoration separately; Reviewer network timeout remains inconclusive
without its required evidence. No new model receipt can supply that proof.

Self-review: budgets and immutable identities are separated; no new client
operation or broader system authority; existing core unchanged. Independent
SPEC/QUALITY review and complete executable plan remain required. Nothing in
this addendum enables an exemption or closes R2/R3 acceptance.

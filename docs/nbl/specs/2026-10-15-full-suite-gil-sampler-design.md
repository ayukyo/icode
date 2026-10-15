# Full-suite GIL-held diagnostic sampler design

Date: 2026-10-15. Status: design candidate only; no implementation credit.

## Approval and scope

Root authorized this design and its companion implementation plan, not actual
TEST/SOURCE/CI changes. Use the existing authoritative WSL checkout; no worktree,
branch, commit or push in this document-authoring turn. Brainstorming,
writing-plans and SDD defaults do not override this restriction. Subsequent
implementation is serial, with independently authored TEST and SOURCE and
separate SPEC/QUALITY gates. Current analysis HEAD is
`b341cb1f010942d99f56861f9eff0ff60f84fc57`; its CI is a separate evidence object.

The real problem is a full-suite Python 3.11 process exiting 139, not a quota
rejection or an established 120-second collector hang. Existing diagnostics
already enable fatal handlers and arm a repeating C watchdog. Only that
diagnostic sampling mechanism changes. Product behavior, unittest discovery,
test selection, Python matrix, permissions and CI's 25-minute hard budget stay.

## Evidence baseline and claims

Runtime: Agent `71bde770aae1b1e79f14e5ea55d999978ef17be3`, pinned Skill
`21566a589cbe98bd35372a04bbb6ca1c51d8eed2`, GitHub Python 3.11 job
`116126826362`, Python 3.11.17/x64. The original decoded log has 409137
characters. UTC window: full-suite launch 2026-10-14 21:57:40.293; six repeating
120-second dumps; last dump 22:09:40.328; shell SIGSEGV 22:09:45.762, exit139.
The last stack ends in a partial File record and has no Fatal Python error
header. A GitHub VM has no applicable physical-device acceptance identity.
Earlier dumps continued normally; the last test's name and sampling time do
not establish that test hung for 120 seconds. No full-suite success footer.

Independent WSL Python 3.11.17 software observations, with child core limit
zero and outer 15-second deadline: repeating 0.05-second C sampling plus the
existing collector method crashed with returncode -11; pure software_fixture
without collector/mock/native also crashed, after six dumps. Same pure loop
2000 times without periodic sampling exited0 (1.137s). Collector three times
without periodic sampling passed with every global patch restored. Python
thread plus synchronous dump_traceback made 23 dumps while those three methods
passed and the thread joined. Root independently repeated pure-fixture C-timer
failure and the no-timer control. These are accelerated diagnostic observations,
not formal regression assertions and not exact reproduction of a 120s period.
The two relevant fixture functions are byte-identical to runtime71. The local
interpreter build differs from the hosted build; no native C stack was captured.

| Claim | Classification | Ceiling |
|---|---|---|
| C-periodic sampling plus pure fixture can crash local 3.11.17 | observed | real SIGSEGV, no intentional fault injection/core |
| Global collector mocks or native quota are necessary | refuted by minimization | pure fixture is sufficient locally |
| Runtime71 is the identical low-level pointer race | supported candidate, unresolved | needs original C-stack or equivalent decisive evidence |
| Fatal handler was not enabled on71 | refuted | fixed71 runner calls enable before arming |
| New sampler is a complete C-watchdog equivalent | false | GIL-held C-extension hangs are a blind spot |
| Proposed change repairs all139 or completes Mac quota | unobserved | requires candidate-bound CI; no Mac credit here |

## Primary-source mechanism, observed 2026-10-15

CPython [v3.11.17 faulthandler.c](https://github.com/python/cpython/blob/v3.11.17/Modules/faulthandler.c#L564-L592)
has a native watchdog thread which blocks signals and calls the thread-stack
dumper without acquiring the GIL. Its
[traceback.c](https://github.com/python/cpython/blob/v3.11.17/Python/traceback.c#L1174-L1250)
reads active interpreter frame/code metadata. The synchronous Python entry point
does not release the GIL. Upstream
[#116008](https://github.com/python/cpython/issues/116008) documents 3.11
faulthandler stack-reading crashes; [#158200](https://github.com/python/cpython/issues/158200)
documents a watchdog metadata race on main/3.16, not a proven 3.11 fix.
This mechanism supports investigation, but does not identify the exact faulting
instruction in the hosted job. No upstream implementation is copied; no
dependency, license or system privilege is added. Adopt the GIL-held synchronous
entry mechanism, defer exact interpreter-memory attribution, reject copying
upstream C internals or suppressing failed tests.

## Alternatives and selected architecture

1. Selected: one Python Thread waits on Event.wait(120), then synchronously calls
   faulthandler.dump_traceback(file=captured_stderr, all_threads=True). Small,
   standard-library-only, and exercised by a real software control. It does not
   inspect another Python thread while that thread owns the GIL.
2. Retain or shorten the C watchdog: rejected; the minimized local crash still
   uses that mechanism. Increasing timeout or skipping the collector hides the
   interaction rather than replacing it.
3. New signal/external watchdog service: deferred; larger platform/lifecycle
   surface, new authority or orchestration, outside this diagnostic slice.

## Contract

Capture sys.stderr once before starting the worker. Retain that same live object
through stop and join, even if suite code temporarily replaces sys.stderr.
Keep faulthandler.enable(file=stream, all_threads=True) before starting. Do not
call dump_traceback_later or cancel_dump_traceback_later and install no signal.
Keep TRACE_INTERVAL_SECONDS=120 without a CLI/environment/configuration knob.

The worker is named full-suite-stack-sampler, daemon=True as a final process-exit
safeguard, but daemon status never substitutes for normal stop/join. Each wait
returning false emits a constant Periodic full-suite stack sample header,
flushes the captured stream, then calls synchronous dump_traceback with all
threads. This is a periodic sample, not proof of a timeout or a failed method.

The lifecycle try/finally includes sampler.start, not just suite execution.
A startup failure before launch or after the real thread starts remains the
primary failure; cleanup still sets stop and attempts join. An unstarted-thread
join error is secondary and must not replace that original startup failure.
There is no claim that asynchronous interruption inside Thread.start provides
an atomic launch/cancel operation: stop prevents any later worker from sampling,
its closure retains the stream, and inability to join is a diagnostic failure,
not thread-cleanup acceptance. No success is reported on any startup failure.

The main thread preserves cwd import visibility, sys.argv, sys.path, default
unittest discovery, verbose output and suite exits. In finally, set the Event,
then join the worker before releasing references or restoring argv/path. A
diagnostic exception is collected, not silently treated as successful sampling.
Success means normal return or SystemExit whose code is None or an integer zero
(including False). SystemExit(0.0) and SystemExit("0") are nonzero Python exits,
despite float0.0 comparing equal to zero. After a successful suite, raise the
first captured non-Exception BaseException unchanged (including KeyboardInterrupt,
which retains interrupt/130 semantics); only ordinary diagnostic/cleanup
Exception failures become RuntimeError with a fixed non-sensitive message. If the
suite already has a nonzero SystemExit or another exception, preserve that exact
exception/exit; best-effort report the diagnostic failure without printing
exception values/locals. Cleanup exceptions are not allowed to turn failure
into exit0. A blocked output write/join may still require CI's hard timeout;
there is no false claim of forcible thread cancellation or a new local budget.

## Capability and security boundary

A Python sampler cannot run while a C extension permanently holds the GIL. It
also cannot guarantee diagnostics when stderr is blocked, the runtime is already
corrupt, or the process is killed. Fatal signal handlers remain enabled, and
GitHub's unchanged 25-minute job limit remains the outer hard bound. No new
signal, subprocess monitor, core dump, permissions or environment settings.
Stack dumps do not intentionally disclose locals; do not format exception values
into new diagnostic messages. Existing unittest error reporting is unchanged.

## Acceptance and serial handoff

Review history: the first plan's same-process semantic harness had a real I1.
An independent outer live sampler could enter its global faulthandler mock,
producing a foreign-stream observation and a genuine fixed-stream Assertion.
That invalidates the earlier zero-review conclusion for that harness, not the
historical incident observations. The revised harness runs every semantic case
and every global mock in an explicit helper subprocess with a 15-second outer
timeout; it never default-discovers the project in that child. Parent tests only
launch the helper and assert its JSON. They must not mock globals, stop the real
outer sampler, or filter foreign observations. Cross-process results contain
only exception type/integer exit, booleans and worker metadata, no exception
values, locals or raw stacks. A failing old SOURCE still returns a safe metadata
record and yields a parent Assertion; no old C timer is armed.
The next different QUALITY review was C0/I2/M0: equality-based success detection
misclassified SystemExit(0.0), and successful-suite cleanup KeyboardInterrupt
was replaced by RuntimeError. Root independently confirmed both. Revised
subprocess subcases cover None/False/0/1/7/0.0/"0" and a single injected
KeyboardInterrupt object raised after a real join. Child-only identity booleans
prove original suite/interrupt precedence without sending their values. These
two corrections remain subject to fresh dual review; no actual TEST/SOURCE is
implemented or verified by changing this document.

Preserve all five existing diagnostics test methods' meanings: discovery and
exit/status, imports/PYTHONPATH, fatal enable, startup/stop ordering, periodic
stacks/no locals, child reap, and CI wiring/guards. Replace only the old ARM/
CANCEL implementation-specific observation with real Thread start/join probes.
Add independent semantic tests that forbid both old C-watchdog APIs before the
runner starts, exercise real short-interval synchronous stacks plus 2000 pure
fixture calls, fixed stderr, joined worker, and sampling/cleanup failure exits.
Do not require an incidental sample to land in software_fixture or any specific
frame; the existing sleeping tiny child independently establishes stack content.
Add startup-before-launch and startup-after-real-launch failure controls.
No regression deliberately crashes a process or asserts SIGSEGV.

The plan supplies complete assets. Before SOURCE, formal RED selects only the
new semantic module and the old instrumented timer/hang methods, which forbid
both C-timer APIs. Do not run old uninstrumented tiny/import tests at that stage:
their old runner still arms its original 120s C timer. After SOURCE, run all
old five methods plus the new module. TEST author and different SOURCE author
must not weaken the independent oracle together. Dual TEST review precedes
SOURCE; dual SOURCE review precedes root integration/docs; global SPEC then
QUALITY precede a candidate push. Local checks are targeted only. Wait until
all b341 same-repository runs are terminal before the next push, not before
writing TEST or implementing an approved source slice. No cancel/rerun masking.
Candidate full-suite 3.11/3.12 evidence must bind new SHA/jobs/raw logs/exits.
Passing short software tests alone is neither full-suite nor native acceptance.

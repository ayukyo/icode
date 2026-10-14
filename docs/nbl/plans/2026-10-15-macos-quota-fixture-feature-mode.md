# Mac B quota fixture feature selection

Date: 2026-10-15. Baseline: 71bde770aae1b1e79f14e5ea55d999978ef17be3.

## Actual failure and sources

CI 38644172530: Intel B 116127916429 and ARM B 116127916452 each
ran 15 methods with one compilation Assertion, zero errors and five original
native skips. RLIMIT_NPROC is undeclared in the software quota probe. The
previous collector/gets failures no longer appear; neither the new strict2
step nor Shared B native ran, and there is no B artifact. Root obtained raw
logs of 32056 and 32315 characters respectively. No quota verdict follows.

Apple's fixed XNU xnu-12377.1.9
[resource.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/sys/resource.h#L487-L491)
exposes the process limit only in its full Darwin feature namespace.
[cdefs.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.1.9/bsd/sys/cdefs.h#L966-L980)
selects the strict POSIX namespace when POSIX is requested without the Darwin
extension selector. Root checked these primary sources on 2026-10-15; this
is upstream mechanism evidence, not an exact installed SDK/header binding.
No upstream implementation is copied, dependency added or quota changed.

## Serial minimal implementation

Root first adds one portable regression to the existing fixture regression
file. It injects an independent preprocessor prerequisite before the first
system header, invokes the real existing software compiler/probe and preserves
the original seventeen fake-API checks. Expect three total regression methods:
two existing passes and one new Assertion on the unchanged baseline fixture.
The model enforces explicit feature selection; it does not emulate the SDK.

After independent TEST review, a different author adds only
`#define _DARWIN_C_SOURCE 1` before the quota probe's system headers. Preserve
the POSIX selector, source file, seventeen checks/footer, original fifteen
methods and collector containment. Do not alter the other deadline C probe,
native quota implementation, budgets, permissions or skip conditions.

After SOURCE review, root updates the existing strict CI regression count
from two to three and adds this plan to B's provenance sources. Keep all
previous source paths and steps; the new strict3 gate should run before the
original selector so fixture prerequisites are independently reported.
Run strict3 and the original software selector (ten passes/five native skips),
then minimal secret/submodule checks and independent whole-candidate review.

Only push main after all 71bde77 same-repository runs terminate; no rerun or
cancel. Dual Mac must compile the real SDK and run the unchanged baseline and
SOURCE vectors to earn their respective native evidence. Passing this POSIX
model alone does not prove SDK compatibility or native quota correctness.

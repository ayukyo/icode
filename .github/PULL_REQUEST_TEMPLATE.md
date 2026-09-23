## Problem and scope

<!-- What real problem does this solve? What is intentionally out of scope? -->

## Changes

<!-- List the smallest meaningful changes. -->

## Verification

<!-- Include exact commands, exit codes, and relevant evidence. -->

- [ ] Focused tests pass
- [ ] `python -m unittest` passes, or skipped checks are explained below
- [ ] `python scripts/preflight.py` passes
- [ ] Documentation/site links pass `python scripts/check_site.py` when applicable

## Evidence boundary

<!-- Separate tested, untested, and environment-dependent claims. -->

## Safety and compatibility

- [ ] No credentials, private ticket contents, logs, or generated local state are committed
- [ ] ICODE-SKILL remains the single workflow/control-plane source of truth
- [ ] New side effects are guarded, receipted, and fail closed
- [ ] Isolation claims match the backend actually tested
- [ ] Backward compatibility and affected callers were reviewed

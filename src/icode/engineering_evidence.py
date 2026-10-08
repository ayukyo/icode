"""Bridge frozen host observations to bounded public engineering receipts.

The public projection omits paths, argv, environment values and output streams.
Digest claims do not authenticate the process or the quality of its tests.
"""

from __future__ import annotations

from dataclasses import fields

from .engineering_verification import (
    EngineeringCheckResult, EngineeringVerificationRun, VerificationCheck, VerificationPlan,
    parse_test_result,
)
from .pack_verify import (
    _ENGINEERING_BINDING_TEXT_FIELDS, _ENGINEERING_COVERAGE,
    _engineering_digest, _engineering_text, engineering_receipt_values, validate_engineering_receipt,
)
from .self_verify import VerificationEvidence


def _budget(value: object) -> None:
    # Reuse the production byte/structure budget before hashing or thawing.
    from .evidence import EvidenceError, _encode_verification_json_bounded
    try:
        _encode_verification_json_bounded(value, too_large_message="engineering input too large",
                                          invalid_message="invalid engineering input")
    except (EvidenceError, TypeError, OverflowError, RecursionError):
        raise ValueError("engineering evidence exceeds its shape/byte budget") from None


def _freeze(value: object) -> tuple | str | int | float | bool | None:
    if type(value) is dict:
        return ("object", tuple((key, _freeze(item)) for key, item in value.items()))
    if type(value) is list:
        return ("array", tuple(_freeze(item) for item in value))
    if type(value) in (str, int, float, bool, type(None)):
        return value
    raise ValueError("engineering facts must contain frozen JSON scalars")


def _thaw(value: object) -> object:
    if type(value) in (str, int, float, bool, type(None)):
        return value
    if type(value) is not tuple or len(value) != 2 or type(value[1]) is not tuple:
        raise ValueError("invalid frozen engineering facts")
    tag, items = value
    if tag == "object":
        result = {}
        for pair in items:
            if type(pair) is not tuple or len(pair) != 2 or type(pair[0]) is not str or pair[0] in result:
                raise ValueError("invalid frozen engineering object")
            result[pair[0]] = _thaw(pair[1])
        return result
    if tag == "array":
        return [_thaw(item) for item in items]
    raise ValueError("invalid frozen engineering container")


def _public_binding(evidence: VerificationEvidence, execution_attempt: str, *, digests: bool = True) -> dict:
    binding = {name: getattr(evidence, name) for name in _ENGINEERING_BINDING_TEXT_FIELDS
               if name not in {"verify_kind", "execution_attempt"}}
    for value in binding.values():
        _engineering_text(value)
    binding.update(verify_kind=evidence.kind, execution_attempt=execution_attempt,
                   exit_code=evidence.exit_code,
                   command_sha256=_engineering_digest(list(evidence.command)) if digests else "0" * 64,
                   artifact_hashes_sha256=_engineering_digest(dict(sorted(evidence.artifact_hashes.items()))) if digests else "0" * 64,
                   output_sha256=evidence.output_sha256 if digests else "0" * 64)
    return binding


def engineering_receipt(evidence: VerificationEvidence) -> dict:
    """Derive current base bindings; frozen facts never shadow later tree binds."""
    source = {k: v for k, v in vars(evidence).items() if k not in {"output", "raw_error"}}
    _budget(source)
    facts = _thaw(evidence.engineering_facts)
    if type(facts) is not dict or set(facts) != {"public_plan", "run"}:
        raise ValueError("invalid engineering fact fields")
    # The execution label is needed to construct the schema candidate. Check
    # its container and value before indexing unvalidated frozen observations.
    if type(facts["run"]) is not dict:
        raise ValueError("invalid engineering run facts")
    execution_attempt = facts["run"].get("attempt")
    _engineering_text(execution_attempt, required=True, maximum=256)
    binding = _public_binding(evidence, execution_attempt, digests=False)
    row = {"kind": "engineering_verification", "schema_version": 1,
           "coverage": dict(_ENGINEERING_COVERAGE), "binding": binding,
           "public_plan": facts["public_plan"], "run": facts["run"],
           "public_projection_digest": "", "fingerprint": "", "repair_fingerprint": "",
           "category": evidence.category, "passed": False}
    engineering_receipt_values(row, compute_digests=False)
    row["binding"] = _public_binding(evidence, execution_attempt)
    values = engineering_receipt_values(row)
    row.update({k: v for k, v in values.items() if k != "binding_exit_code"})
    # Category and aggregate exit are derived by the producer, never guessed
    # from old command output or overwritten by subsequently supplied labels.
    if evidence.category != values["category"] or evidence.exit_code != values["binding_exit_code"]:
        raise ValueError("engineering base outcome contradicts frozen observations")
    validate_engineering_receipt(row)
    return row


def build_engineering_evidence(
    plan: VerificationPlan, run: EngineeringVerificationRun, *, binding: VerificationEvidence,
) -> VerificationEvidence:
    """Bind exactly one host-owned frozen plan/run, not a file or model report."""
    if type(plan) is not VerificationPlan or type(run) is not EngineeringVerificationRun or type(binding) is not VerificationEvidence:
        raise ValueError("engineering evidence requires exact host plan/run/binding types")
    if binding.engineering_facts is not None or binding.step != run.step or binding.attempt != run.attempt:
        raise ValueError("engineering execution identity does not match binding")
    if binding.tested_worktree_fingerprint != run.source_after:
        raise ValueError("engineering tested source binding does not match source_after")
    if type(run.checks) is not tuple or len(run.checks) != len(plan.checks) or any(type(c) is not EngineeringCheckResult for c in run.checks):
        raise ValueError("engineering results must match frozen checks")
    # Reject attacker-sized base values and streams before any digest work.
    _budget({k: v for k, v in vars(binding).items() if k not in {"output", "raw_error", "engineering_facts"}})
    if type(plan.checks) is not tuple or not 1 <= len(plan.checks) <= 16 or any(type(c) is not VerificationCheck for c in plan.checks):
        raise ValueError("invalid frozen engineering plan checks")
    _budget({"workspace_root": str(plan.workspace_root), "workspace_identity": plan.workspace_identity,
             "run_id": plan.run_id, "ticket_id": plan.ticket_id, "steps": plan.steps,
             "platforms": plan.platforms, "environment": plan.environment,
             "checks": [c._record() for c in plan.checks]})
    for value in (plan.run_id, plan.ticket_id):
        _engineering_text(value, required=True, maximum=256)
    _budget({"run": {k: v for k, v in vars(run).items() if k != "checks"},
             "checks": [{k: v for k, v in vars(c).items() if k != "output"} for c in run.checks]})
    for check, result in zip(plan.checks, run.checks):
        if result.check_id != check.check_id:
            raise ValueError("engineering check identities or order do not match")
        if result.output is not None and (type(result.output) is not bytes or len(result.output) > check.output_limit_bytes):
            raise ValueError("engineering output is not complete bounded bytes")
        if result.status == "passed" and check.kind == "test" and (
            result.output is None or parse_test_result(check.adapter, result.output) != result.tests_passed
        ):
            raise ValueError("engineering passed test count does not match reported stream")
    public_plan = {
        "run_id": plan.run_id, "ticket_id": plan.ticket_id,
        "workspace_sha256": "0" * 64, "environment_sha256": "0" * 64,
        "steps": list(plan.steps), "platforms": list(plan.platforms),
        "checks": [{"check_id": c.check_id, "kind": c.kind, "adapter": c.adapter,
                    "required": c.required, "tool_sha256": c.executable_identity,
                    "parameters_sha256": "0" * 64,
                    "timeout_seconds": c.timeout_seconds, "output_limit_bytes": c.output_limit_bytes}
                   for c in plan.checks],
    }
    facts_run = {name: getattr(run, name) for name in (
        "plan_digest", "step", "attempt", "status", "source_before", "source_after", "os_enforced")}
    facts_run["checks"] = [dict(
        {k: v for k, v in vars(c).items() if k != "output"},
        output_sha256="0" * 64 if c.output is not None else "", output_bytes=len(c.output) if c.output is not None else 0,
    ) for c in run.checks]
    facts = {"public_plan": public_plan, "run": facts_run}
    _budget(facts)
    base = {f.name: getattr(binding, f.name) for f in fields(VerificationEvidence)}
    base.update(exit_code=None, category="side_effect_unknown")
    provisional = VerificationEvidence(**base)
    # Build a provisional public binding solely to let the shared validator
    # derive outcome. The final evidence retains current host base fields.
    projected_binding = _public_binding(provisional, run.attempt, digests=False)
    row = dict(kind="engineering_verification", schema_version=1, coverage=dict(_ENGINEERING_COVERAGE),
               binding=projected_binding, public_plan=public_plan, run=facts_run,
               public_projection_digest="", category="side_effect_unknown", passed=False,
               fingerprint="", repair_fingerprint="")
    values = engineering_receipt_values(row, compute_digests=False)
    # Closed fields and every size/count limit have passed before the first
    # identity or raw-output digest is computed. Placeholders never escape.
    digest = plan.digest
    if run.plan_digest != digest:
        raise ValueError("engineering run does not bind the frozen plan")
    public_plan["workspace_sha256"] = _engineering_digest({"root": str(plan.workspace_root), "identity": plan.workspace_identity})
    public_plan["environment_sha256"] = _engineering_digest(plan.environment)
    for check, projected in zip(plan.checks, public_plan["checks"]):
        projected["parameters_sha256"] = _engineering_digest({"argv": check.argv, "cwd": check.cwd})
    for result, projected in zip(run.checks, facts_run["checks"]):
        projected["output_sha256"] = result.output_sha256
    base.update(engineering_facts=_freeze(facts), exit_code=values["binding_exit_code"], category=values["category"])
    evidence = VerificationEvidence(**base)
    if plan.digest != digest:
        raise ValueError("engineering plan changed during evidence binding")
    engineering_receipt(evidence)
    return evidence

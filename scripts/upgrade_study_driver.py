"""Serialization-only audit correction, separately sealed; frozen study source stays intact."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_upgrade_study as study


original_audit = study.audit


def audit_json(result, instance, variant, seed, baseline):
    # Both operands use the saved JSON representation: tuples become arrays.
    # All validator, method, config, reference, timing and trace checks remain active.
    result = json.loads(json.dumps(result, allow_nan=False))
    baseline = json.loads(json.dumps(baseline, allow_nan=False))
    return original_audit(result, instance, variant, seed, baseline)


def sealed(output):
    study.locked(output)
    path = output / "audit_amendment.lock.json"
    value = {"schema_version": 1,
        "protocol_sha256": study.digest(output / "protocol.lock.json"),
        "driver_sha256": study.digest(Path(__file__)),
        "reason": "Pilot final verification exposed tuple/list equality in objective_config after JSON reload",
        "correction": "Normalize result and independently recomputed B0 to JSON before original audit",
        "scope": "audit representation only; no solver, seed, schedule, config, input or stored solution change",
        "holdout_exposure": "zero holdout runs at amendment creation"}
    if path.exists():
        if study.read(path) != value:
            raise RuntimeError("Audit driver or amendment changed")
        if study.read(output / "audit_amendment.sha256.json")["sha256"] != study.digest(path):
            raise RuntimeError("Audit amendment hash mismatch")
    else:
        if (output / "raw/holdout").exists():
            raise RuntimeError("Cannot introduce this audit amendment after holdout starts")
        study.create(path, value)
        study.create(output / "audit_amendment.sha256.json", {"sha256": study.digest(path)})
        destination = output / "source/scripts/upgrade_study_driver.py"
        destination.write_bytes(Path(__file__).read_bytes())
    study.audit = audit_json


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("pilot", "holdout", "verify-pilot", "verify"))
    parser.add_argument("--output", type=Path, default=ROOT / "results/high_score_upgrade_20261010")
    args = parser.parse_args()
    sealed(args.output)
    if args.action.startswith("verify"):
        study.verify(args.output, "pilot")
        if args.action == "verify":
            study.verify(args.output, "holdout")
    else:
        study.run_stage(args.output, args.action)

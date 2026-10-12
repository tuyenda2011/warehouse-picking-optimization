"""Portable audited evidence and shared statistics for reports and the demo.

Only raw instances and solver results are stored. Tables are always reconstructed;
validation proves internal consistency, not authorship of an uploaded experiment.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from statistics import mean, median, stdev

from .benchmark_archive import METRICS, STOCHASTIC, TIMING_KEYS, _assert_same, verify_benchmark
from .models import InputError, Instance, read_instance
from .search import SearchConfig, canonical_search_config
from .solver import METHODS, fingerprint
from .units import unit_label
from .validator import validate_solution

KIND = "warehouse_benchmark_evaluation"
DEFAULT_METHODS = ["B0", "B2", "LNS", "ALNS", "VNS"]
METRIC_KEYS = (*METRICS[:-1], "batches", "used_pickers")


def _finite(value, label, minimum=0):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < minimum):
        raise InputError(f"{label}: expected a finite number >= {minimum}")
    return value


def _json_value(value):
    return json.loads(json.dumps(value, allow_nan=False))


def _validate_trace(result):
    search = result["search"]
    trace = search.get("trace", [])
    if not isinstance(trace, list):
        raise InputError("Search trace must be a list")
    last_time, last_cost, last_iteration = -1., float("inf"), -1
    for point in trace:
        seconds = _finite(point["seconds"], "trace.seconds")
        cost = _finite(point["objective"], "trace.objective")
        iteration = point.get("iteration", 0)
        if type(iteration) is not int or iteration < last_iteration:
            raise InputError("Trace iterations must be nondecreasing integers")
        if seconds < last_time or cost > last_cost + 1e-7:
            raise InputError("Trace must have increasing time and nonincreasing best F")
        last_time, last_cost, last_iteration = seconds, cost, iteration
    if trace:
        if not math.isclose(last_cost, result["metrics"]["objective"], abs_tol=1e-7, rel_tol=1e-7):
            raise InputError("Trace endpoint does not match the final objective")
        if last_time > result["timing"]["optimization_seconds"] + 1e-6:
            raise InputError("Trace exceeds recorded optimization time")
        if "initial_objective" in search and not math.isclose(
                trace[0]["objective"], search["initial_objective"], abs_tol=1e-7, rel_tol=1e-7):
            raise InputError("Trace initialization objective mismatch")


def validate_evaluation(payload):
    """Audit every route, objective, identity, seed and recorded trace before use."""
    try:
        if (not isinstance(payload, dict) or type(payload.get("schema_version")) is not int
                or payload["schema_version"] != 1 or payload.get("kind") != KIND):
            raise InputError("Unsupported evaluation schema or kind")
        if (not isinstance(payload.get("preset"), str) or not payload["preset"]
                or not isinstance(payload.get("created_at_utc"), str)
                or not isinstance(payload.get("provenance"), dict)):
            raise InputError("Evaluation requires preset, created_at_utc and provenance metadata")
        datetime.fromisoformat(payload["created_at_utc"])
        groups = payload.get("groups")
        if not isinstance(groups, list) or not groups:
            raise InputError("Evaluation requires at least one dataset group")
        names = set()
        for group in groups:
            name = group["name"]
            if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name)
                    or name.casefold() in names):
                raise InputError("Dataset group names must be unique simple identifiers")
            names.add(name.casefold())
            config = group["config"]
            if not isinstance(config, dict):
                raise InputError("Dataset config must be an object")
            methods = config.get("methods", DEFAULT_METHODS)
            seeds = config.get("search_seeds", [7])
            if (not isinstance(methods, list) or not methods or "B0" not in methods
                    or any(m not in METHODS for m in methods) or len(set(methods)) != len(methods)):
                raise InputError("Evaluation methods must be unique supported methods including B0")
            if (not isinstance(seeds, list) or not seeds or any(type(s) is not int for s in seeds)
                    or len(set(seeds)) != len(seeds)):
                raise InputError("Search seeds must be unique integers")
            options = _json_value(asdict(SearchConfig(**config.get("search", {})).validate()))
            data = group["instances"]
            if not isinstance(data, list) or not data:
                raise InputError("Dataset group has no instances")
            instances = [Instance.from_dict(item) for item in data]
            by_name = {instance.name: instance for instance in instances}
            if len({n.casefold() for n in by_name}) != len(instances):
                raise InputError("Duplicate instance names in evaluation")
            hashes = {n: fingerprint(i) for n, i in by_name.items()}
            _assert_same(group.get("instance_fingerprints"), hashes, "Evaluation input inventory")
            results = group["results"]
            if not isinstance(results, list) or not results:
                raise InputError("Dataset group has no results")
            identities, baselines = set(), {}
            for result in results:
                n, method, seed = result["instance"], result["method"], result["search"]["seed"]
                if n not in by_name or method not in methods or type(seed) is not int:
                    raise InputError("Unexpected result identity")
                identity = (n, method, seed)
                if identity in identities:
                    raise InputError("Duplicate result identity")
                identities.add(identity)
                if result.get("feasible") is not True:
                    raise InputError("Evaluation cannot include infeasible results")
                if result.get("instance_sha256") != hashes[n]:
                    raise InputError("Instance fingerprint mismatch")
                errors = validate_solution(by_name[n], result)
                if errors:
                    raise InputError(f"Invalid result {name}/{n}/{method}: {'; '.join(errors)}")
                _assert_same(canonical_search_config(result["search"]["config"]), options, "Search configuration")
                for key in TIMING_KEYS:
                    _finite(result["timing"][key], f"timing.{key}")
                for key in METRICS[:-1]:
                    _finite(result["metrics"][key], f"metrics.{key}")
                iterations = result["search"].get("iterations_completed", 0)
                if type(iterations) is not int or not 0 <= iterations <= options["iterations"]:
                    raise InputError("Invalid completed iteration count")
                _validate_trace(result)
                if method == "B0":
                    baselines[n] = result
            expected = {(n, m, s) for n in by_name for m in methods
                        for s in (seeds if m in STOCHASTIC else seeds[:1])}
            if identities != expected:
                raise InputError("Missing or unexpected evaluation runs/seeds")
            for result in results:
                instance = by_name[result["instance"]]
                baseline = baselines[instance.name]["metrics"]
                completion = max(baseline["makespan"], 1.)
                objective = {"distance_ref": max(baseline["distance"], 1.),
                             "completion_ref": completion,
                             "tardiness_ref": len(instance.orders) * completion,
                             "weights": config.get("weights", [1/3, 1/3, 1/3])}
                _assert_same(_json_value(result["objective_config"]), _json_value(objective), "Objective configuration")
        from .sensitivity import validate_conditions
        validate_conditions(payload)
        return payload
    except InputError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise InputError(f"Malformed evaluation data: {exc}") from exc


def make_evaluation(groups, preset="custom", provenance=None):
    groups = deepcopy(groups)
    for group in groups:
        group.setdefault("instance_fingerprints", {
            data["name"]: fingerprint(Instance.from_dict(data)) for data in group["instances"]})
    payload = {"schema_version": 1, "kind": KIND, "preset": preset,
               "created_at_utc": datetime.now(timezone.utc).isoformat(),
               "provenance": deepcopy(provenance or {}), "groups": groups}
    return validate_evaluation(payload)


def load_evaluation(path_or_bytes):
    def reject_constant(value):
        raise InputError(f"Nonfinite JSON value: {value}")
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise InputError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    try:
        if isinstance(path_or_bytes, (bytes, bytearray)):
            content = bytes(path_or_bytes).decode("utf-8-sig")
        else:
            content = Path(path_or_bytes).read_text(encoding="utf-8-sig")
        return validate_evaluation(json.loads(content, parse_constant=reject_constant,
                                               object_pairs_hook=unique_object))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InputError(f"Invalid evaluation JSON: {exc}") from exc


def load_benchmark_group(path, name):
    verified = verify_benchmark(Path(path))
    return {"name": name, "config": deepcopy(verified["config"]),
            "instances": [read_instance(p).to_dict() for p in sorted((verified["root"] / "instances").glob("*.json"))],
            "instance_fingerprints": {r["instance"]: r["instance_sha256"] for r in verified["results"]},
            "results": deepcopy(verified["results"]),
            "provenance": {"source_sha256": verified["manifest"]["source_sha256"],
                           "environment": {k: verified["manifest"].get(k) for k in ("python", "platform", "cpu")}}}


def snapshot_evaluation(snapshot):
    from .demo_snapshot import validate_snapshot
    validate_snapshot(snapshot)
    results = list(snapshot["results"].values())
    seed = results[0]["search"]["seed"]
    config = {"methods": list(snapshot["results"]), "search_seeds": [seed],
              "weights": list(results[0]["objective_config"]["weights"]),
              "search": deepcopy(results[0]["search"]["config"])}
    return make_evaluation([{"name": "current_run", "config": config,
                             "instances": [snapshot["instance"]], "results": results}], preset="live")


def improvement_pct(value, reference, metric="objective"):
    if reference == 0:
        return None
    direction = 1 if metric == "on_time_rate" else -1
    return 100 * direction * (value - reference) / reference


def evaluation_tables(payload, reference="B2"):
    """Average search seeds first; each paired instance contributes one vote.

    Summary improvement_std is spread between paired instance means, NOT a CI.
    Per-instance metric std is spread over search seeds. Cohorts stay separate.
    Callers validate the payload once before repeatedly filtering/plotting it.
    """
    raw, per_instance, summary = [], [], []
    for group in payload["groups"]:
        instances = {data["name"]: Instance.from_dict(data) for data in group["instances"]}
        grouped = defaultdict(list)
        for result in group["results"]:
            instance = instances[result["instance"]]
            row = {"group": group["name"], "instance": instance.name,
                   "n": len(instance.orders), "instance_seed": instance.metadata.get("seed"),
                   "distance_unit": unit_label(instance, "distance"), "time_unit": unit_label(instance, "time"),
                   "method": result["method"], "search_seed": result["search"]["seed"],
                   "feasible": True,
                   **{key: result["metrics"][key] for key in METRIC_KEYS},
                   **{key: result["timing"][key] for key in TIMING_KEYS},
                   "iterations_completed": result["search"].get("iterations_completed", 0),
                   "search_executed": result["search"].get("search_executed", False),
                   "stop_reason": result["search"].get("stop_reason", "unknown")}
            raw.append(row)
            grouped[(instance.name, result["method"])].append(row)
        by = {}
        for (name, method), runs in sorted(grouped.items()):
            row = {k: runs[0][k] for k in ("group", "instance", "n", "instance_seed", "distance_unit", "time_unit", "method")}
            row.update(reference=reference, runs=len(runs), feasible_rate=1.,
                       zero_iteration_runs=sum(r["iterations_completed"] == 0 for r in runs) if method in STOCHASTIC else None,
                       initialization_seconds_mean=mean(r["initialization_seconds"] for r in runs),
                       search_seconds_mean=mean(r["search_seconds"] for r in runs))
            for metric in METRICS:
                values = [r[metric] for r in runs]
                row.update({f"{metric}_mean": mean(values), f"{metric}_median": median(values),
                            f"{metric}_std": stdev(values) if len(values) > 1 else 0.,
                            f"{metric}_best": max(values) if metric == "on_time_rate" else min(values)})
            by[(name, method)] = row
        for (name, method), row in by.items():
            baseline = by.get((name, reference))
            for metric in METRICS:
                row[f"{metric}_improvement_pct"] = improvement_pct(
                    row[f"{metric}_mean"], baseline[f"{metric}_mean"], metric) if baseline else None
                row[f"{metric}_difference"] = row[f"{metric}_mean"] - baseline[f"{metric}_mean"] if baseline else None
            per_instance.append(row)
        for method in sorted({m for _, m in by}):
            pairs = [row for (n, m), row in by.items() if m == method and (n, reference) in by]
            if not pairs:
                continue
            deltas = [row["objective_difference"] for row in pairs]
            improvements = [row["objective_improvement_pct"] for row in pairs if row["objective_improvement_pct"] is not None]
            row = {"group": group["name"], "method": method, "reference": reference,
                   "instances": len(pairs), "runs": sum(p["runs"] for p in pairs),
                   "win": sum(d < -1e-9 for d in deltas), "tie": sum(abs(d) <= 1e-9 for d in deltas),
                   "loss": sum(d > 1e-9 for d in deltas), "percentage_instances": len(improvements),
                   "mean_improvement_pct": mean(improvements) if improvements else None,
                   "improvement_std": stdev(improvements) if len(improvements) > 1 else None}
            for metric in METRICS:
                values = [p[f"{metric}_improvement_pct"] for p in pairs if p[f"{metric}_improvement_pct"] is not None]
                row[f"{metric}_improvement_pct"] = mean(values) if values else None
                row[f"{metric}_percentage_instances"] = len(values)
            summary.append(row)
    return {"summary": summary, "per_instance": per_instance, "raw_metrics": raw}

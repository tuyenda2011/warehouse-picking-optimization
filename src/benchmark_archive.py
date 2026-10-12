"""Audit portable benchmark archives without importing plotting libraries."""
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from .comparison import paired_comparisons
from .models import InputError, read_instance
from .search import SearchConfig, canonical_search_config
from .solver import fingerprint
from .validator import validate_solution

METRICS = ("objective", "distance", "makespan", "tardiness", "late_orders", "on_time_rate", "total_seconds")
TIMING_KEYS = ("preprocessing_seconds", "initialization_seconds", "search_seconds",
               "optimization_seconds", "validation_seconds", "total_seconds")
STOCHASTIC = {"B3", "LNS", "ALNS", "VNS", "ALNS_NO_SCHEDULE", "ALNS_NO_2OPT"}
FLOAT_TOLERANCE = 1e-10


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _same_number(actual, expected):
    return isinstance(actual, (int, float)) and not isinstance(actual, bool) and math.isclose(
        float(actual), float(expected), rel_tol=FLOAT_TOLERANCE, abs_tol=FLOAT_TOLERANCE
    )


def _assert_same(actual, expected, label):
    if isinstance(expected, float):
        if not _same_number(actual, expected):
            raise InputError(f"{label} mismatch")
        return
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise InputError(f"{label} keys mismatch")
        for key, value in expected.items():
            _assert_same(actual[key], value, f"{label}.{key}")
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise InputError(f"{label} length mismatch")
        for index, value in enumerate(expected):
            _assert_same(actual[index], value, f"{label}[{index}]")
        return
    if actual != expected:
        raise InputError(f"{label} mismatch")


def _safe_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise InputError(f"Manifest path escapes benchmark directory: {relative}")
    return path


def _expected_summaries(results):
    grouped = defaultdict(list)
    for result in results:
        row = {
            "instance": result["instance"],
            "method": result["method"],
            "feasible": result["feasible"],
            **{key: result["metrics"][key] for key in METRICS[:-1]},
            **{key: result["timing"][key] for key in TIMING_KEYS},
            **{key: result["search"][key] for key in (
                "iterations_completed", "stop_reason", "adaptation_updates",
                "adapted_iterations", "search_executed", "budget_scope",
            )},
        }
        grouped[(row["instance"], row["method"])].append(row)
    summaries = []
    for (instance, method), group in sorted(grouped.items()):
        baseline = grouped[(instance, "B0")][0]
        summary = {
            "instance": instance,
            "method": method,
            "runs": len(group),
            "feasible_rate": sum(row["feasible"] for row in group) / len(group),
            "search_diagnostics": {
                "zero_iteration_runs": sum(r["iterations_completed"] == 0 for r in group)
                if method in STOCHASTIC else None,
                "iterations_min": min(r["iterations_completed"] for r in group),
                "iterations_median": statistics.median(r["iterations_completed"] for r in group),
                "adapted_runs": sum(r["adapted_iterations"] > 0 for r in group),
                "initialization_mean_seconds": statistics.mean(r["initialization_seconds"] for r in group),
                "search_mean_seconds": statistics.mean(r["search_seconds"] for r in group),
                "stop_reasons": {
                    reason: sum(r["stop_reason"] == reason for r in group)
                    for reason in sorted({r["stop_reason"] for r in group})
                },
            },
        }
        for metric in METRICS:
            values = [r[metric] for r in group]
            sign = 1 if metric == "on_time_rate" else -1
            average = statistics.mean(values)
            summary[metric] = {
                "mean": average,
                "median": statistics.median(values),
                "std": statistics.stdev(values) if len(values) > 1 else 0.0,
                "best": max(values) if sign == 1 else min(values),
                "difference_vs_B0": average - baseline[metric],
                "improvement_pct_vs_B0": (
                    100 * sign * (average - baseline[metric]) / baseline[metric]
                    if baseline[metric] else None
                ),
            }
        summaries.append(summary)
    return summaries


def verify_benchmark(root: Path):
    """Return validated raw results and aggregates, or raise InputError."""
    root = root.resolve()
    required = ("config.json", "manifest.json", "preregistered.json", "runs.csv", "summary.json", "comparison.json")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise InputError(f"Benchmark is incomplete; missing: {', '.join(missing)}")

    config = read_json(root / "config.json")
    manifest = read_json(root / "manifest.json")
    preregistered = read_json(root / "preregistered.json")
    _assert_same(manifest.get("config"), config, "manifest.json configuration")
    _assert_same(preregistered.get("config"), config, "preregistered.json configuration")
    _assert_same(manifest.get("source_sha256"), preregistered.get("source_sha256"), "source hashes")
    records = manifest.get("runs")
    if not isinstance(records, list) or not records:
        raise InputError("manifest.json has no runs")

    instances, instance_files = {}, {}
    for path in sorted((root / "instances").glob("*.json")):
        instance = read_instance(path)
        if instance.name in instances:
            raise InputError("Duplicate archived instance name")
        instances[instance.name] = instance
        instance_files[instance.name] = path.relative_to(root).as_posix()
    if not instances:
        raise InputError("Benchmark has no instances")
    if "instance_files" in manifest:
        _assert_same(manifest["instance_files"], instance_files, "instance file inventory")

    results = []
    identities = set()
    referenced_files = set()
    for record in records:
        relative = record.get("file")
        if not isinstance(relative, str):
            raise InputError("Manifest run has no relative file")
        path = _safe_path(root, relative)
        if not path.is_file():
            raise InputError(f"Missing raw result: {relative}")
        referenced_files.add(path.resolve())
        result = read_json(path)
        name = result.get("instance")
        if name not in instances:
            raise InputError(f"Raw result references unknown instance: {name}")
        instance = instances[name]
        actual_hash = fingerprint(instance)
        if result.get("instance_sha256") != actual_hash or record.get("instance_sha256") != actual_hash:
            raise InputError(f"Instance fingerprint mismatch: {relative}")
        errors = validate_solution(instance, result)
        if errors:
            raise InputError(f"Invalid raw result {relative}: {'; '.join(errors)}")
        identity = (name, result.get("method"), result.get("search", {}).get("seed"))
        if identity in identities:
            raise InputError(f"Duplicate raw run: {identity}")
        identities.add(identity)
        results.append(result)

    actual_files = {path.resolve() for path in (root / "raw").glob("*.json")}
    if actual_files != referenced_files:
        raise InputError("raw/ contents do not match manifest.json")
    seeds = config.get("search_seeds", [7])
    methods = config.get("methods", ["B0", "B2", "LNS", "ALNS", "VNS"])
    expected_identities = {(name, method, seed) for name in instances for method in methods
                           for seed in (seeds if method in STOCHASTIC else seeds[:1])}
    if identities != expected_identities:
        raise InputError("Missing or unexpected benchmark run identities")
    baselines = {r["instance"]: r for r in results if r["method"] == "B0"}
    for result in results:
        instance = instances[result["instance"]]
        baseline = baselines[result["instance"]]["metrics"]
        completion = max(baseline["makespan"], 1.)
        expected_objective = {"distance_ref": max(baseline["distance"], 1.),
                              "completion_ref": completion, "tardiness_ref": len(instance.orders) * completion,
                              "weights": config.get("weights", [1/3, 1/3, 1/3])}
        _assert_same(result["objective_config"], expected_objective, "objective configuration")
        search_config = canonical_search_config(config.get("search", {}))
        _assert_same(canonical_search_config(result["search"]["config"]), search_config, "search configuration")

    with (root / "runs.csv").open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    if len(csv_rows) != len(results):
        raise InputError("runs.csv row count does not match manifest.json")
    raw_by_identity = {
        (r["instance"], r["method"], int(r["search"]["seed"])): r for r in results
    }
    seen_csv = set()
    for row in csv_rows:
        identity = (row["instance"], row["method"], int(row["search_seed"]))
        if identity in seen_csv or identity not in raw_by_identity:
            raise InputError(f"Unexpected or duplicate runs.csv row: {identity}")
        seen_csv.add(identity)
        raw = raw_by_identity[identity]
        values = {**{key: raw["metrics"][key] for key in METRICS[:-1]},
                  "total_seconds": raw["timing"]["total_seconds"]}
        for key in METRICS:
            if not _same_number(float(row[key]), values[key]):
                raise InputError(f"CSV/raw mismatch: {identity}, {key}")
    if seen_csv != set(raw_by_identity):
        raise InputError("runs.csv is missing raw runs")

    expected_summaries = _expected_summaries(results)
    summaries = read_json(root / "summary.json")
    _assert_same(summaries, expected_summaries, "summary.json")
    comparison_rows = [{"instance": r["instance"], "method": r["method"], "feasible": r["feasible"], **r["metrics"]} for r in results]
    references = tuple(config.get("references", ["B0", "B2", "B3", "LNS", "VNS"]))
    expected_comparison = paired_comparisons(comparison_rows, references)
    comparisons = read_json(root / "comparison.json")
    _assert_same(comparisons, expected_comparison, "comparison.json")

    if preregistered.get("instances") and set(preregistered["instances"]) != set(instances):
        raise InputError("preregistered.json instance set mismatch")
    for name, instance in instances.items():
        if preregistered.get("instances", {}).get(name) != fingerprint(instance):
            raise InputError("Preregistered instance fingerprint mismatch")
    return {
        "root": root,
        "config": config,
        "manifest": manifest,
        "results": results,
        "csv_rows": csv_rows,
        "summaries": summaries,
        "comparisons": comparisons,
    }



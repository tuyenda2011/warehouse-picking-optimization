"""Unified experiment planning, sealed group checkpoints and report-only exports."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .benchmark import STOCHASTIC, benchmark
from .generator import MAP_SCENARIOS, generate, generate_scenario
from .models import InputError, Instance, read_instance, write_json
from .provenance import python_source_hashes
from .search import SearchConfig
from .solver import METHODS, fingerprint

EXPERIMENT_KIND = "warehouse_benchmark_experiment"


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _digest(value):
    raw = json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_hashes():
    return python_source_hashes(Path(__file__).parent)


def _tree_hashes(path):
    return {p.relative_to(path).as_posix(): _file_hash(p)
            for p in sorted(path.rglob("*")) if p.is_file()}


def _merge(base, overrides):
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        result[key] = (_merge(result[key], value)
                       if isinstance(value, dict) and isinstance(result.get(key), dict)
                       else copy.deepcopy(value))
    return result


def _path(value, base):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def is_experiment_config(config):
    return isinstance(config, dict) and (config.get("kind") == EXPERIMENT_KIND or "groups" in config)


def _integers(values, label, positive=False):
    if (not isinstance(values, list) or not values
            or any(type(v) is not int or (positive and v < 1) for v in values)
            or len(values) != len(set(values))):
        raise InputError(f"{label} must be a nonempty list of unique {'positive ' if positive else ''}integers")
    return values


def _datasets(config):
    if "inline_instances" in config:
        if (not isinstance(config["inline_instances"], list) or not config["inline_instances"]
                or config.get("instances") or config.get("scenarios")):
            raise InputError("inline_instances must be a nonempty exclusive input inventory")
        datasets = [Instance.from_dict(data) for data in config["inline_instances"]]
        if len({i.name.casefold() for i in datasets}) != len(datasets):
            raise InputError("Benchmark instance names must be unique (case-insensitive)")
        return datasets
    if config.get("instances") and config.get("scenarios"):
        raise InputError("Benchmark cannot combine instances and scenarios")
    if "instances" in config:
        if not isinstance(config["instances"], list) or not config["instances"]:
            raise InputError("instances must be a nonempty list of input paths")
        datasets = [read_instance(path) for path in config["instances"]]
    elif "scenarios" in config:
        scenarios = config["scenarios"]
        if (not isinstance(scenarios, list) or not scenarios or len(scenarios) != len(set(scenarios))
                or any(s not in MAP_SCENARIOS for s in scenarios)):
            raise InputError("scenarios must contain unique supported scenario names")
        seeds = _integers(config.get("scenario_seeds", [42]), "scenario_seeds")
        overrides = config.get("scenario_overrides", {})
        if not isinstance(overrides, dict):
            raise InputError("scenario_overrides must be an object")
        datasets = [generate_scenario(s, seed=seed, **overrides.get(s, {}))
                    for s in scenarios for seed in seeds]
    else:
        sizes = _integers(config.get("sizes", [20, 50]), "sizes", positive=True)
        seeds = _integers(config.get("instance_seeds", [101]), "instance_seeds")
        datasets = [generate(n=n, seed=seed, **config.get("generator", {}))
                    for n in sizes for seed in seeds]
    names = [i.name.casefold() for i in datasets]
    if len(names) != len(set(names)):
        raise InputError("Benchmark instance names must be unique (case-insensitive)")
    return datasets


def _validate_group_config(config):
    methods = config.setdefault("methods", ["B0", "B2", "LNS", "ALNS", "VNS"])
    if (not isinstance(methods, list) or not methods or "B0" not in methods
            or len(methods) != len(set(methods)) or any(m not in METHODS for m in methods)):
        raise InputError("Benchmark methods must be unique, supported and include B0")
    seeds = _integers(config.setdefault("search_seeds", [7]), "search_seeds")
    _integers(config.get("sizes", [20, 50]), "sizes", positive=True)
    _integers(config.get("instance_seeds", [101]), "instance_seeds")
    SearchConfig(**config.get("search", {})).validate()
    weights = config.get("weights", [1 / 3] * 3)
    if (not isinstance(weights, list) or len(weights) != 3
            or any(type(w) not in (int, float) or not math.isfinite(w) or w <= 0 for w in weights)
            or not math.isclose(sum(weights), 1., rel_tol=1e-9, abs_tol=1e-9)):
        raise InputError("weights must be three finite positive values summing to 1")
    return sum(len(seeds) if m in STOCHASTIC else 1 for m in methods)


def _catalog_config(group, config, base, preset, required):
    catalog_path = _path(group["catalog"], base)
    if not catalog_path.is_file():
        if not required:
            return None, {}, f"Optional catalog unavailable: {catalog_path}"
        raise InputError(f"Requested catalog is missing: {catalog_path}")
    catalog = _read_json(catalog_path)
    entries = catalog.get("instances") if isinstance(catalog, dict) else None
    if (not isinstance(entries, list) or not entries
            or any(not isinstance(e, dict) or not isinstance(e.get("file"), str)
                   or type(e.get("orders")) is not int for e in entries)):
        raise InputError(f"Invalid or empty catalog: {catalog_path}")
    selection = _merge(group.get("selection", {}), group.get("preset_selection", {}).get(preset, {}))
    orders = selection.get("orders")
    if orders is not None:
        _integers(orders, "catalog selection orders", positive=True)
    limit = selection.get("limit_per_size", 0)
    if type(limit) is not int or limit < 0:
        raise InputError("catalog limit_per_size must be a nonnegative integer")
    selected, per_size = [], {}
    for entry in sorted(entries, key=lambda e: (e["orders"], e["file"])):
        n = entry["orders"]
        if orders is not None and n not in orders:
            continue
        if limit and per_size.get(n, 0) >= limit:
            continue
        selected.append(entry)
        per_size[n] = per_size.get(n, 0) + 1
    if not selected:
        raise InputError(f"No catalog instances selected: {catalog_path}")
    hashes, paths = {str(catalog_path): _file_hash(catalog_path)}, []
    for entry in selected:
        path = _path(entry["file"], base)
        if not path.is_file():
            raise InputError(f"Requested catalog input is missing: {path}")
        actual = _file_hash(path)
        instance = read_instance(path)
        if len(instance.orders) != entry["orders"]:
            raise InputError(f"Catalog order count mismatch: {path}")
        # The existing Kris catalog's sha256 identifies its original raw file.
        expected_hash = instance.metadata.get("source_sha256") if entry.get("raw_file") else actual
        if entry.get("sha256") and entry["sha256"] != expected_hash:
            raise InputError(f"Catalog input provenance SHA-256 mismatch: {path}")
        if entry.get("raw_file"):
            raw_path = _path(entry["raw_file"], base)
            if raw_path.is_file():
                raw_hash = _file_hash(raw_path)
                if entry.get("sha256") and entry["sha256"] != raw_hash:
                    raise InputError(f"Catalog raw source SHA-256 mismatch: {raw_path}")
                hashes[str(raw_path)] = raw_hash
        hashes[str(path)] = actual
        paths.append(str(path))
    config["instances"] = paths
    return config, hashes, None


def resolve_experiment(config, preset="quick", config_path=None, groups=None):
    """Validate every selected input and count runs without creating files or solving."""
    if not is_experiment_config(config):
        raise InputError("Unified experiment config requires a groups list")
    definitions = config.get("groups")
    if not isinstance(definitions, list) or not definitions:
        raise InputError("Experiment groups must be a nonempty list")
    names = [g.get("name") if isinstance(g, dict) else None for g in definitions]
    if (any(not isinstance(n, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", n) for n in names)
            or len({n.casefold() for n in names}) != len(names)):
        raise InputError("Experiment group names must be unique safe directory names")
    if groups is not None and (not groups or len(groups) != len(set(groups)) or set(groups) - set(names)):
        raise InputError(f"Unknown or duplicate requested groups; choose {', '.join(names)}")
    presets = config.get("presets", {})
    if preset not in presets:
        raise InputError(f"Unknown experiment preset: {preset}")
    base = Path(config_path).resolve().parent if config_path else Path.cwd()
    base = _path(config.get("base_dir", "."), base)
    common = _merge(config.get("defaults", {}), presets[preset])
    resolved, skipped, input_hashes = [], [], {}
    for definition in definitions:
        name = definition["name"]
        if groups is not None and name not in groups:
            skipped.append({"name": name, "reason": "Not selected by --groups"})
            continue
        group_config = _merge(common, definition.get("config", {}))
        group_config = _merge(group_config, definition.get("presets", {}).get(preset, {}))
        if "catalog" in definition:
            group_config, hashes, reason = _catalog_config(
                definition, group_config, base, preset,
                required=groups is not None or not definition.get("optional", False))
            if reason:
                skipped.append({"name": name, "reason": reason})
                continue
            input_hashes.update(hashes)
        elif "instances" in group_config:
            paths = [_path(p, base) for p in group_config["instances"]]
            for path in paths:
                if not path.is_file():
                    raise InputError(f"Requested input is missing: {path}")
                input_hashes[str(path)] = _file_hash(path)
            group_config["instances"] = [str(p) for p in paths]
        runs_per_instance = _validate_group_config(group_config)
        datasets = _datasets(group_config)
        resolved.append({"name": name, "config": group_config,
                         "instances": len(datasets), "runs": len(datasets) * runs_per_instance,
                         "instance_sha256": {i.name: fingerprint(i) for i in datasets}})
    if not resolved:
        raise InputError("No experiment groups are available")
    primary_instances = sum(g["instances"] for g in resolved)
    extra = []
    if "sensitivity" in config:
        from .sensitivity import expand_conditions
        extra = expand_conditions(resolved, config["sensitivity"], preset, _datasets)
        resolved.extend(extra)
    return {"schema_version": 1, "kind": EXPERIMENT_KIND, "preset": preset,
            "purpose": "pipeline/demo evidence only" if preset == "quick" else "report experiment",
            "groups": resolved, "skipped_groups": skipped, "input_sha256": input_hashes,
            "request_sha256": _digest(config), "instances": sum(g["instances"] for g in resolved),
            "runs": sum(g["runs"] for g in resolved),
            "primary_instances": primary_instances,
            "sensitivity_cases": sum(g["instances"] for g in extra),
            "sensitivity_runs": sum(g["runs"] for g in extra),
            "search_budget_seconds": sum(g["instances"] * len(g["config"]["search_seeds"])
                                         * sum(m in STOCHASTIC for m in g["config"]["methods"])
                                         * g["config"].get("search", {}).get("seconds", 3.)
                                         for g in resolved)}


def dry_run(config, preset="quick", config_path=None, groups=None):
    if is_experiment_config(config):
        return resolve_experiment(config, preset, config_path, groups)
    if groups:
        raise InputError("--groups is available only for unified experiment configs")
    suite = {"groups": [{"name": "benchmark", "config": config}], "presets": {"custom": {}}}
    return resolve_experiment(suite, "custom")


def _atomic_manifest(output, manifest):
    temporary = output / f".manifest-{uuid4().hex}.json"
    write_json(temporary, manifest)
    temporary.replace(output / "manifest.json")


class _RootSealError(InputError):
    pass


def _root_seal_guard(output):
    root_stat = output.lstat()
    root_identity = (root_stat.st_dev, root_stat.st_ino)
    headers = {output / name: _file_hash(output / name)
               for name in ("config.json", "preregistered.json")}

    def check():
        try:
            current = output.lstat()
        except OSError as exc:
            raise _RootSealError(f"Experiment output root missing or unreadable: {output}; "
                                 "stop output cleanup and preserve the remaining evidence") from exc
        if (not stat.S_ISDIR(current.st_mode)
                or (current.st_dev, current.st_ino) != root_identity):
            raise _RootSealError(f"Experiment output root replaced: {output}; "
                                 "preserve the original directory and use a new output for another run")
        for path, expected in headers.items():
            try:
                actual = _file_hash(path)
            except OSError as exc:
                raise _RootSealError(f"Experiment root metadata missing or unreadable: {path}; "
                                     "stop output cleanup and preserve the remaining evidence") from exc
            if actual != expected:
                raise _RootSealError(f"Experiment root metadata changed: {path}; "
                                     "preserve the sealed metadata and use a new output for changed settings")

    return check


def _record_failure(output, manifest, record, exc):
    if isinstance(exc, _RootSealError):
        return
    status = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
    record["status"] = status
    manifest.update(status=status, last_error={"type": type(exc).__name__, "message": str(exc),
                                             "path": record["path"]})
    _atomic_manifest(output, manifest)


def _read_seal(output):
    missing = [name for name in ("config.json", "preregistered.json", "manifest.json")
               if not (output / name).is_file()]
    if missing:
        raise InputError(f"Experiment is incomplete; missing: {', '.join(missing)}")
    config = _read_json(output / "config.json")
    identity = _read_json(output / "preregistered.json")
    manifest = _read_json(output / "manifest.json")
    if (manifest.get("kind") != EXPERIMENT_KIND or manifest.get("schema_version") != 1
            or identity.get("config") != config or manifest.get("identity_sha256") != _digest(identity)
            or manifest.get("config_sha256") != _digest(config)
            or manifest.get("source_sha256") != identity.get("source_sha256")
            or manifest.get("input_sha256") != config.get("input_sha256")):
        raise InputError("Experiment configuration or preregistered seal mismatch")
    return config, identity, manifest


def _audit_group(path, expected, identity, hashes):
    from .evaluation import load_benchmark_group
    name = expected["name"]
    if not path.is_dir() or _tree_hashes(path) != hashes:
        raise InputError(f"Completed group evidence hash mismatch: {name}")
    group = load_benchmark_group(path, name)
    archived = _read_json(path / "preregistered.json")
    if (group["config"] != expected["config"]
            or archived.get("instances") != expected["instance_sha256"]
            or archived.get("source_sha256") != identity["source_sha256"]):
        raise InputError(f"Completed group configuration, source or input mismatch: {name}")
    return group


def _audit_groups(output, config, identity, manifest, require_complete=False, pending=()):
    expected = {g["name"]: g for g in config["groups"]}
    completed = manifest.get("completed_groups", {})
    if (not isinstance(completed, dict) or set(completed) - set(expected)
            or (require_complete and (manifest.get("status") != "complete" or set(completed) != set(expected)))):
        raise InputError("Experiment is incomplete or contains unexpected group checkpoints")
    dataset_root = output / "datasets"
    actual = {p.name for p in dataset_root.iterdir()} if dataset_root.exists() else set()
    if actual != set(completed) | set(pending):
        raise InputError("Experiment datasets do not match completed group checkpoints")
    groups = []
    for name in expected:
        if name not in completed:
            continue
        path = dataset_root / name
        groups.append(_audit_group(path, expected[name], identity, completed[name]))
    return groups


def _checkpoint_path(output, relative):
    path = (output / relative).resolve()
    if not path.is_relative_to(output) or path == output:
        raise InputError("Checkpoint path escapes experiment directory")
    return path


def _recover_groups(output, config, identity, manifest):
    expected = {g["name"]: g for g in config["groups"]}
    completed = manifest["completed_groups"]
    recoveries = {}
    for record in manifest["attempts"]:
        name = record["group"]
        if not record.get("validated_sha256") or name in completed:
            continue
        if name not in expected or name in recoveries:
            raise InputError("Unexpected or duplicate validated group checkpoint")
        destination = output / "datasets" / name
        attempt = _checkpoint_path(output, record["path"])
        path = destination if destination.exists() else attempt
        recoveries[name] = (record, path, destination)
    if not recoveries:
        return
    promoted = [name for name, (_, path, destination) in recoveries.items() if path == destination]
    # Audit every existing completed group and every pending group before mutation.
    _audit_groups(output, config, identity, manifest, pending=promoted)
    for name, (record, path, _) in recoveries.items():
        _audit_group(path, expected[name], identity, record["validated_sha256"])
    for name, (record, path, destination) in recoveries.items():
        if path != destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
            path.rename(destination)
        completed[name] = record["validated_sha256"]
        record.update(status="complete", path=destination.relative_to(output).as_posix())
        _atomic_manifest(output, manifest)


def _report_matches(path, record, payload):
    from .evaluation import load_evaluation
    if not path.is_dir() or _tree_hashes(path) != record.get("validated_sha256"):
        return False
    try:
        return load_evaluation(path / "evaluation.json") == payload
    except (InputError, OSError, json.JSONDecodeError):
        return False


def _complete_report(output, manifest, record, started):
    report = output / "report"
    record.update(status="complete", path="report")
    manifest.update(status="complete", evaluation_sha256=_file_hash(output / "evaluation.json"),
                    report="report", report_sha256=_tree_hashes(report),
                    elapsed_seconds=manifest.get("elapsed_seconds", 0) + time.perf_counter() - started)
    _atomic_manifest(output, manifest)


def _recover_report(output, manifest, payload, started):
    report = output / "report"
    for record in reversed(manifest.get("report_attempts", [])):
        if not record.get("validated_sha256"):
            continue
        path = report if report.exists() else _checkpoint_path(output, record["path"])
        if _report_matches(path, record, payload):
            if path != report:
                path.rename(report)
            _complete_report(output, manifest, record, started)
            return True
    if report.exists():
        # Preserve an orphan that has no trustworthy completed-export checkpoint.
        preserved = output / "_report_attempts" / uuid4().hex
        record = {"path": preserved.relative_to(output).as_posix(), "status": "preserved",
                  "reason": "Unsealed orphan report preserved before re-export"}
        manifest.setdefault("report_attempts", []).append(record)
        _atomic_manifest(output, manifest)
        preserved.parent.mkdir(parents=True, exist_ok=True)
        report.rename(preserved)
    return False


def _evaluation(config, identity, groups):
    from .evaluation import make_evaluation
    provenance = {"experiment_identity_sha256": _digest(identity),
                  "source_sha256": identity["source_sha256"], "input_sha256": config["input_sha256"],
                  "purpose": config["purpose"], "skipped_groups": config["skipped_groups"],
                  "checkpoint_policy": "Audited complete groups reused; interrupted attempts preserved and group restarted"}
    return make_evaluation(groups, preset=config["preset"], provenance=provenance)


def _saved_evaluation(output, config, identity, manifest, groups):
    from .evaluation import load_evaluation
    path = output / "evaluation.json"
    if not path.is_file() or manifest.get("evaluation_sha256") != _file_hash(path):
        raise InputError("Experiment evaluation.json is missing or its evidence hash differs")
    payload = load_evaluation(path)
    expected = _evaluation(config, identity, groups)
    for key in ("preset", "groups", "provenance"):
        if payload.get(key) != expected[key]:
            raise InputError(f"Experiment evaluation.json {key} differs from audited evidence")
    return payload


def run_experiment(config, output, preset="quick", config_path=None, groups=None,
                   resume=False, progress=None, presentation=False, charts=True):
    """Run sequential low-level groups; preserve attempts and resume audited group checkpoints."""
    from .evaluation_report import export_evaluation
    resolved = resolve_experiment(config, preset, config_path, groups)
    identity = {"config": resolved, "source_sha256": _source_hashes()}
    output = Path(output).resolve()
    started = time.perf_counter()
    if resume:
        if not output.is_dir():
            raise InputError("--resume requires an existing sealed experiment directory")
        saved_config, saved_identity, manifest = _read_seal(output)
        if saved_config != resolved:
            raise InputError("Resume configuration or input fingerprint mismatch")
        if saved_identity != identity:
            raise InputError("Resume source fingerprint mismatch")
        check_root = _root_seal_guard(output)
        check_root()
        _recover_groups(output, resolved, identity, manifest)
        audited = _audit_groups(output, resolved, identity, manifest)
        check_root()
        if manifest.get("status") == "complete":
            payload = _saved_evaluation(output, resolved, identity, manifest, audited)
            check_root()
            return payload
        for record in manifest["attempts"]:
            if record["status"] == "started":
                record["status"] = "interrupted"
        manifest["status"] = "running"
        _atomic_manifest(output, manifest)
    else:
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise InputError("Experiment requires a new or empty directory; refusing to overwrite evidence")
        output.mkdir(parents=True, exist_ok=True)
        write_json(output / "config.json", resolved)
        write_json(output / "preregistered.json", identity)
        manifest = {"schema_version": 1, "kind": EXPERIMENT_KIND, "status": "running",
                    "created_at_utc": datetime.now(timezone.utc).isoformat(),
                    "identity_sha256": _digest(identity), "config_sha256": _digest(resolved),
                    "source_sha256": identity["source_sha256"], "input_sha256": resolved["input_sha256"],
                    "preset": preset, "purpose": resolved["purpose"],
                    "instances": resolved["instances"], "runs": resolved["runs"],
                    "completed_groups": {}, "attempts": [], "skipped_groups": resolved["skipped_groups"]}
        _atomic_manifest(output, manifest)
        audited = []
        check_root = _root_seal_guard(output)
    for group in resolved["groups"]:
        check_root()
        name = group["name"]
        if name in manifest["completed_groups"]:
            continue
        attempt = output / "_attempts" / name / uuid4().hex
        record = {"group": name, "path": attempt.relative_to(output).as_posix(), "status": "started"}
        manifest["attempts"].append(record)
        _atomic_manifest(output, manifest)

        def guarded_progress(row, name=name):
            check_root()
            try:
                if progress is not None:
                    progress({"group": name, **row})
            finally:
                check_root()

        try:
            check_root()
            benchmark(group["config"], attempt, progress=guarded_progress)
            check_root()
            hashes = _tree_hashes(attempt)
            _audit_group(attempt, group, identity, hashes)
            check_root()
            destination = output / "datasets" / name
            record.update(status="validated", validated_sha256=hashes)
            _atomic_manifest(output, manifest)
            destination.parent.mkdir(parents=True, exist_ok=True)
            attempt.rename(destination)
        except (Exception, KeyboardInterrupt) as exc:
            _record_failure(output, manifest, record, exc)
            raise
        record.update(status="complete", path=destination.relative_to(output).as_posix())
        manifest["completed_groups"][name] = hashes
        _atomic_manifest(output, manifest)
    # Audit all saved groups before exporting, including groups reused on resume.
    check_root()
    audited = _audit_groups(output, resolved, identity, manifest)
    payload = _evaluation(resolved, identity, audited)
    check_root()
    evaluation_path = output / "evaluation.json"
    if evaluation_path.exists():
        from .evaluation import load_evaluation
        saved = load_evaluation(evaluation_path)
        if any(saved.get(key) != payload[key] for key in ("preset", "groups", "provenance")):
            raise InputError("Existing evaluation differs from audited groups; refusing to overwrite evidence")
        payload = saved
    else:
        write_json(evaluation_path, payload)
    report = output / "report"
    check_root()
    if _recover_report(output, manifest, payload, started):
        check_root()
        return payload
    report_attempt = output / "_report_attempts" / uuid4().hex
    report_record = {"path": report_attempt.relative_to(output).as_posix(), "status": "started"}
    manifest.setdefault("report_attempts", []).append(report_record)
    _atomic_manifest(output, manifest)
    try:
        check_root()
        export_evaluation(payload, report_attempt, presentation=presentation, charts=charts)
        check_root()
        report_record.update(status="validated", validated_sha256=_tree_hashes(report_attempt))
        manifest["evaluation_sha256"] = _file_hash(evaluation_path)
        _atomic_manifest(output, manifest)
        report_attempt.rename(report)
    except (Exception, KeyboardInterrupt) as exc:
        _record_failure(output, manifest, report_record, exc)
        raise
    check_root()
    _complete_report(output, manifest, report_record, started)
    return payload


def load_report_input(path):
    """Load portable JSON, a completed experiment or an audited legacy benchmark."""
    from .evaluation import load_benchmark_group, load_evaluation, make_evaluation
    path = Path(path).resolve()
    if path.is_file():
        return load_evaluation(path)
    if not path.is_dir():
        raise InputError(f"Report input is missing: {path}")
    manifest_path = path / "manifest.json"
    config_path = path / "config.json"
    is_experiment = ((manifest_path.is_file() and _read_json(manifest_path).get("kind") == EXPERIMENT_KIND)
                     or (config_path.is_file() and _read_json(config_path).get("kind") == EXPERIMENT_KIND))
    if is_experiment:
        config, identity, manifest = _read_seal(path)
        groups = _audit_groups(path, config, identity, manifest, require_complete=True)
        return _saved_evaluation(path, config, identity, manifest, groups)
    if (path / "evaluation.json").is_file():
        return load_evaluation(path / "evaluation.json")
    return make_evaluation([load_benchmark_group(path, path.name)], preset="custom",
                           provenance={"benchmark": str(path)})


def export_report(source, output, presentation=False, charts=True):
    from .evaluation_report import export_evaluation
    payload = load_report_input(source)
    return export_evaluation(payload, output, presentation=presentation, charts=charts)

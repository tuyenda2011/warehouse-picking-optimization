"""Clustered uncertainty, isolated routing and instrumented memory diagnostics."""
import argparse
import csv
import json
import math
import random
import statistics
import sys
import time
import tracemalloc
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import run_research as study
from scripts.build_comparison_report import _assert_same, verify_benchmark
from src.evaluator import Evaluator
from src.generator import generate
from src.heuristics import fcfs, list_schedule
from src.models import InputError, Order, read_instance, write_json
from src.search import SearchConfig
from src.solver import fingerprint, solve
from src.validator import validate_solution


def percentile(values, probability):
    position = (len(values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def clustered_uncertainty(pairs, clusters, strata, seed=20261001, samples=10000):
    """Average sizes within seed, then bootstrap seed clusters within conditions."""
    grouped = defaultdict(list)
    for pair in pairs:
        if pair["improvement_pct"] is not None:
            grouped[clusters[pair["instance"]]].append(pair["improvement_pct"])
    values = {cluster: statistics.mean(rows) for cluster, rows in grouped.items()}
    if not values:
        raise InputError("No nonzero reference objectives for inference")
    cells = defaultdict(list)
    for cluster, value in values.items():
        cells[strata[cluster]].append(value)
    rng = random.Random(seed)
    draws = sorted(statistics.mean(value for cell in cells.values()
                                   for value in rng.choices(cell, k=len(cell)))
                   for _ in range(samples))
    wins = sum(value > 1e-9 for value in values.values())
    losses = sum(value < -1e-9 for value in values.values())
    n = wins + losses
    p = min(1., 2 * sum(math.comb(n, i) for i in range(min(wins, losses) + 1)) / 2**n) if n else 1.
    return {"instances": len(pairs), "clusters": len(values), "strata": len(cells),
            "mean_improvement_pct": statistics.mean(values.values()),
            "bootstrap_95_pct": [percentile(draws, .025), percentile(draws, .975)],
            "bootstrap_seed": seed, "bootstrap_samples": samples,
            "cluster_win": wins, "cluster_loss": losses, "cluster_tie": len(values) - n,
            "two_sided_sign_p": p}


def uncertainty_rows(comparisons, instances, options):
    clusters = {name: instance.metadata["seed"] for name, instance in instances.items()}
    strata = {instance.metadata["seed"]: (instance.metadata["layout"]["type"],
                                         instance.metadata["due_dates"]["tightness"])
              for instance in instances.values()}
    rows = []
    for pair in comparisons:
        if pair["method"] == "ALNS":
            row = clustered_uncertainty(pair["pairs"], clusters, strata,
                                        options["bootstrap_seed"], options["bootstrap_samples"])
            row.update(method="ALNS", reference=pair["reference"])
            rows.append(row)
    running = 0.
    for index, row in enumerate(sorted(rows, key=lambda r: r["two_sided_sign_p"])):
        running = max(running, min(1., (len(rows) - index) * row["two_sided_sign_p"]))
        row["holm_sign_p"] = running
    return rows


def routing_instance(count, cross, seed):
    instance = generate(1, seed, aisles=4, rows=4, cross_aisles=cross, pickers=1, capacity=100)
    chosen = random.Random(seed).sample(instance.products, count)
    instance.products = chosen
    instance.orders = [Order("routing-order", {p.id: 1 for p in chosen}, 100., 0)]
    instance.name = f"routing-k{count}-cross{cross}-seed{seed}"
    return instance.validate()


def reference_objective(instance):
    ctx = Evaluator(instance)
    plan = list_schedule(ctx, fcfs(ctx), "nn")
    ctx.set_reference(plan)
    return json.loads(json.dumps(asdict(ctx.objective)))


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit_solution(root, path, instance):
    result = study.read(path)
    errors = validate_solution(instance, result)
    if result.get("instance_sha256") != fingerprint(instance):
        errors.append("Instance fingerprint mismatch")
    if errors:
        raise InputError(f"{path.relative_to(root)}: {errors}")
    return result


def run_diagnostics(study_root, output):
    study_root, output = Path(study_root).resolve(), Path(output).resolve()
    if output.exists():
        raise InputError("Diagnostics require a new output directory")
    locked = study.checked_protocol(study_root)
    study.verify(study_root, locked)
    options = locked["protocol"]["diagnostics"]
    output.mkdir(parents=True)
    study.seal(output / "diagnostics.lock.json", {
        "protocol_sha256": study.digest(study_root / "protocol.lock.json"),
        "options": options, "source_sha256": study.source_hashes(),
        "memory_note": "tracemalloc peak is traced Python allocations, not process RSS; runtime is instrumented",
        "inference_note": "Resample demand seeds within layout/deadline cells; average sizes within seed first."
    })
    verified = verify_benchmark(study_root / "holdout")
    instances = {p.stem: read_instance(p) for p in (study_root / "holdout/instances").glob("*.json")}
    uncertainty = uncertainty_rows(verified["comparisons"], instances, options)
    write_json(output / "uncertainty.json", uncertainty)

    records, routing_rows, memory_rows = [], [], []
    for count in options["routing_locations"]:
        for cross in options["routing_cross_aisles"]:
            for seed in options["routing_seeds"]:
                instance = routing_instance(count, cross, seed)
                input_path = output / "instances" / f"{instance.name}.json"
                write_json(input_path, instance.to_dict())
                ctx = Evaluator(instance)
                plan = list_schedule(ctx, fcfs(ctx), "nn")
                ctx.set_reference(plan)
                case = []
                for mode in ("nn", "2opt", "exact"):
                    ctx.router.cache.clear()
                    ctx.info_cache.clear()
                    started = time.perf_counter()
                    route = ctx.router.route({p.location for p in instance.products}, mode)
                    seconds = time.perf_counter() - started
                    result = ctx.evaluate(plan, mode, details=True)
                    result.update(method=f"ROUTE_{mode}", feasible=True,
                                  instance_sha256=fingerprint(instance), routing_seconds=seconds)
                    path = output / "raw" / f"{instance.name}-{mode}.json"
                    write_json(path, result)
                    audit_solution(output, path, instance)
                    records.append({"file": path.relative_to(output).as_posix(),
                                    "instance_file": input_path.relative_to(output).as_posix(),
                                    "sha256": study.digest(path)})
                    case.append({"instance": instance.name, "locations": count, "cross_aisles": cross,
                                 "seed": seed, "routing": mode, "distance": route.distance,
                                 "routing_seconds": seconds})
                optimum = case[-1]["distance"]
                for row in case:
                    row["gap_pct"] = 100 * (row["distance"] - optimum) / optimum
                    if row["gap_pct"] < -1e-7:
                        raise InputError("Routing heuristic scored below exact")
                routing_rows.extend(case)
                print(f"Routing k={count} cross={cross} seed={seed}: exact={optimum:g}", flush=True)
    write_csv(output / "routing.csv", routing_rows)

    config = SearchConfig(**{**study.selection(study_root), "seconds": 0,
                             "iterations": options["memory_iterations"]})
    for n in options["memory_sizes"]:
        profile_seed = locked["protocol"]["holdout"]["instance_seeds"][0]
        instance = next(i for i in instances.values() if len(i.orders) == n and i.metadata["seed"] == profile_seed)
        input_path = output / "instances" / f"{instance.name}.json"
        write_json(input_path, instance.to_dict())
        tracemalloc.start()
        try:
            started = time.perf_counter()
            result = solve(instance, "ALNS", 201, config)
            instrumented_seconds = time.perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        result["memory_profile"] = {"peak_traced_bytes": peak, "instrumented": True,
                                    "fixed_iterations": config.iterations,
                                    "instrumented_seconds": instrumented_seconds}
        path = output / "raw" / f"memory-n{n}.json"
        write_json(path, result)
        audit_solution(output, path, instance)
        records.append({"file": path.relative_to(output).as_posix(),
                        "instance_file": input_path.relative_to(output).as_posix(), "sha256": study.digest(path)})
        memory_rows.append({"orders": n, "iterations": result["search"]["iterations_completed"],
                            "peak_traced_mib": peak / 1024**2,
                            "instrumented_seconds": instrumented_seconds,
                            "cost_evaluations": result["search"]["cost_evaluations"]})
        print(f"Memory n={n}: {peak / 1024**2:.2f} MiB traced", flush=True)
    write_csv(output / "memory.csv", memory_rows)
    output_files = {p.name: study.digest(p) for p in (output / "uncertainty.json", output / "routing.csv", output / "memory.csv")}
    study.seal(output / "manifest.lock.json", {"solutions": records, "tables": output_files})
    verify_diagnostics(study_root, output)
    lines = ["# Bằng chứng bổ sung cho chương trình", "",
             "36 instance theo 3 kích thước × 2 layout × 2 độ nới hạn × 3 seed nhu cầu. "
             "12 nhóm seed dùng trong suy luận; không coi seed tìm kiếm là quan sát độc lập.", "",
             "Bootstrap phân tầng theo layout/deadline, lấy mẫu nhóm seed và giữ ba kích thước cùng nhóm. "
             "Khoảng 95% là ước lượng trên thiết kế đã chạy; kiểm định dấu xét hướng cải thiện, "
             "bỏ hòa, hai phía và hiệu chỉnh Holm cho bốn đối chứng. Không suy ra khả năng thắng mọi kho.", "",
             "| Đối chứng | Cải thiện F (%) | Bootstrap 95% | Holm p (dấu) |",
             "|---|---:|---|---:|"]
    for row in uncertainty:
        low, high = row["bootstrap_95_pct"]
        lines.append(f"| {row['reference']} | {row['mean_improvement_pct']:.3f} | [{low:.3f}, {high:.3f}] | {row['holm_sign_p']:.5f} |")
    lines += ["", "routing.csv: gap quãng đường cho NN/2-opt/exact trên 12 tập điểm 6 hoặc 8 vị trí; "
              "giữ cùng chuyến, không gán gap tuyến cho tối ưu joint.", "",
              "memory.csv: peak bộ nhớ Python do tracemalloc theo dõi ở số vòng cố định. "
              "Không phải RAM toàn tiến trình; thời gian có overhead instrumentation, không so với benchmark thường."]
    (output / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def finite_nonnegative(value, label):
    if (not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(value) or value < 0):
        raise InputError(f"Invalid {label}")


def verify_csv(path, expected_rows, retained_times=()):
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        if reader.fieldnames != list(expected_rows[0]) or len(rows) != len(expected_rows):
            raise InputError(f"Diagnostics CSV shape mismatch: {path.name}")
    for index, (actual, expected) in enumerate(zip(rows, expected_rows)):
        for key, value in expected.items():
            label = f"{path.name} row {index + 1}.{key}"
            if isinstance(value, (int, float)) or key in retained_times:
                try:
                    number = float(actual[key])
                except (TypeError, ValueError) as error:
                    raise InputError(f"Invalid {label}") from error
                if key in retained_times and value is None:
                    finite_nonnegative(number, label)
                else:
                    _assert_same(number, float(value), label)
            elif actual[key] != value:
                raise InputError(f"{label} mismatch")


def expected_diagnostics(options, instances, protocol):
    specs = {}
    for count in options["routing_locations"]:
        for cross in options["routing_cross_aisles"]:
            for seed in options["routing_seeds"]:
                instance = routing_instance(count, cross, seed)
                for mode in ("nn", "2opt", "exact"):
                    specs[instance.name, f"ROUTE_{mode}"] = {
                        "instance": instance, "locations": count, "cross_aisles": cross,
                        "seed": seed, "routing": mode}
    profile_seed = protocol["holdout"]["instance_seeds"][0]
    for count in options["memory_sizes"]:
        selected = [i for i in instances.values()
                    if len(i.orders) == count and i.metadata["seed"] == profile_seed]
        if len(selected) != 1:
            raise InputError("Memory diagnostics have no unique registered instance")
        specs[selected[0].name, "ALNS"] = {"instance": selected[0], "orders": count}
    return specs


def routing_table(specs, results):
    rows, exact_distances = [], {}
    for identity, spec in specs.items():
        if "routing" not in spec:
            continue
        result = results[identity]
        instance, mode = spec["instance"], spec["routing"]
        ctx = Evaluator(instance)
        plan = list_schedule(ctx, fcfs(ctx), "nn")
        _assert_same(result["plan"], json.loads(json.dumps(plan)), "Routing fixed plan")
        _assert_same(result["routing"], mode, "Routing decoder identity")
        distance = ctx.router.route({p.location for p in instance.products}, mode).distance
        _assert_same(result["metrics"]["distance"], distance, "Routing decoder distance")
        finite_nonnegative(result["routing_seconds"], "routing runtime")
        rows.append({"instance": instance.name, "locations": spec["locations"],
                     "cross_aisles": spec["cross_aisles"], "seed": spec["seed"],
                     "routing": mode, "distance": distance,
                     "routing_seconds": result["routing_seconds"]})
        if mode == "exact":
            exact_distances[instance.name] = distance
    for row in rows:
        optimum = exact_distances[row["instance"]]
        row["gap_pct"] = 100 * (row["distance"] - optimum) / optimum
        if row["gap_pct"] < -1e-7:
            raise InputError("Routing heuristic scored below exact")
    return rows


def memory_table(specs, results, config):
    rows = []
    expected_config = json.loads(json.dumps(asdict(config)))
    for identity, spec in specs.items():
        if "orders" not in spec:
            continue
        result = results[identity]
        search, memory = result["search"], result["memory_profile"]
        _assert_same(search["seed"], 201, "Memory search seed")
        _assert_same(search["config"], expected_config, "Memory search configuration")
        _assert_same(search["iterations_completed"], config.iterations, "Memory completed iterations")
        if memory.get("instrumented") is not True or memory.get("fixed_iterations") != config.iterations:
            raise InputError("Memory profile protocol mismatch")
        peak, evaluations = memory["peak_traced_bytes"], search["cost_evaluations"]
        if type(peak) is not int or type(evaluations) is not int:
            raise InputError("Memory peak and evaluations must be integer measurements")
        finite_nonnegative(peak, "memory peak")
        finite_nonnegative(evaluations, "memory cost evaluations")
        instrumented_seconds = memory.get("instrumented_seconds")
        if instrumented_seconds is not None:
            finite_nonnegative(instrumented_seconds, "instrumented runtime")
        rows.append({"orders": spec["orders"], "iterations": search["iterations_completed"],
                     "peak_traced_mib": peak / 1024**2, "instrumented_seconds": instrumented_seconds,
                     "cost_evaluations": evaluations})
    return rows


def verify_diagnostics(study_root, output):
    """Rebuild statistics and tables; legacy instrumented time is checksum-only."""
    study_root, output = Path(study_root).resolve(), Path(output).resolve()
    study_locked = study.checked_protocol(study_root, mode="audit")
    protocol = study_locked["protocol"]
    locked = study.checked_seal(output / "diagnostics.lock.json")
    if locked["protocol_sha256"] != study.digest(study_root / "protocol.lock.json"):
        raise InputError("Diagnostics refer to a different study")
    _assert_same(locked["options"], protocol["diagnostics"], "Diagnostics options")
    _assert_same(locked["source_sha256"], study_locked["source_sha256"], "Diagnostics historical source")
    options = locked["options"]
    verified = verify_benchmark(study_root / "holdout")
    expected_source = {name.removeprefix("src/"): checksum for name, checksum in study_locked["source_sha256"].items()
                       if name.startswith("src/")}
    _assert_same(verified["manifest"]["source_sha256"], expected_source, "Diagnostics benchmark historical source")
    declared_instances = [read_instance(study_root / entry["file"]) for entry in study_locked["datasets"]["holdout"]]
    instances = {instance.name: instance for instance in declared_instances}
    if {r["instance"] for r in verified["results"]} != set(instances):
        raise InputError("Diagnostics holdout instance set mismatch")
    for result in verified["results"]:
        _assert_same(result["instance_sha256"], fingerprint(instances[result["instance"]]),
                     "Diagnostics registered holdout instance")
    expected_config = study.benchmark_config(study_root, study_locked, "holdout", study.selection(study_root))
    _assert_same({k: v for k, v in verified["config"].items() if k != "instances"},
                 {k: v for k, v in expected_config.items() if k != "instances"}, "Diagnostics holdout configuration")
    _assert_same(study.read(output / "uncertainty.json"),
                 uncertainty_rows(verified["comparisons"], instances, options), "Uncertainty/holdout")
    specs = expected_diagnostics(options, instances, protocol)
    manifest = study.checked_seal(output / "manifest.lock.json")
    if len(manifest["solutions"]) != len(specs):
        raise InputError("Missing diagnostics solutions")
    files, inputs, results = set(), set(), {}
    for record in manifest["solutions"]:
        path = (output / record["file"]).resolve()
        input_path = (output / record["instance_file"]).resolve()
        if not path.is_relative_to(output) or not input_path.is_relative_to(output) or path in files:
            raise InputError("Invalid or duplicate diagnostics path")
        files.add(path)
        inputs.add(input_path)
        if study.digest(path) != record["sha256"]:
            raise InputError("Diagnostics raw result changed")
        instance = read_instance(input_path)
        result = audit_solution(output, path, instance)
        identity = result["instance"], result["method"]
        if identity not in specs or identity in results:
            raise InputError("Unexpected or duplicate diagnostics identity")
        _assert_same(fingerprint(instance), fingerprint(specs[identity]["instance"]), "Diagnostics input protocol")
        _assert_same(result["objective_config"], reference_objective(instance), "Diagnostics objective configuration")
        results[identity] = result
    if set(results) != set(specs):
        raise InputError("Missing diagnostics identities")
    if files != {p.resolve() for p in (output / "raw").glob("*.json")}:
        raise InputError("Diagnostics raw file set mismatch")
    if inputs != {p.resolve() for p in (output / "instances").glob("*.json")}:
        raise InputError("Diagnostics input file set mismatch")
    if set(manifest["tables"]) != {"uncertainty.json", "routing.csv", "memory.csv"}:
        raise InputError("Diagnostics table set mismatch")
    for name, checksum in manifest["tables"].items():
        if study.digest(output / name) != checksum:
            raise InputError("Diagnostics table changed")
    verify_csv(output / "routing.csv", routing_table(specs, results))
    config = SearchConfig(**{**study.selection(study_root), "seconds": 0,
                             "iterations": options["memory_iterations"]}).validate()
    memory_rows = memory_table(specs, results, config)
    verify_csv(output / "memory.csv", memory_rows, ("instrumented_seconds",))
    legacy_times = sum(row["instrumented_seconds"] is None for row in memory_rows)
    print(f"Revalidated {len(specs)} diagnostics solutions and recomputed statistics/tables; "
          f"{legacy_times} legacy instrumented runtimes have a finite nonnegative value and sealed checksum "
          f"(remaining {len(memory_rows) - legacy_times} runtimes rebuilt from raw)", flush=True)
    return len(specs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify_diagnostics(args.study.resolve(), args.output.resolve())
    else:
        run_diagnostics(args.study, args.output)

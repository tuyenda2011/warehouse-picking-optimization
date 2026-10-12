"""Reproducible experiment runner with raw results and per-instance paired summaries."""
import csv
import hashlib
import json
import os
import platform
import re
import random
import stat
import statistics
import time
from collections import defaultdict
from pathlib import Path

from .comparison import paired_comparisons
from .generator import MAP_SCENARIOS, generate, generate_scenario
from .models import InputError, Instance, read_instance, write_json
from .provenance import python_source_hashes
from .search import SearchConfig
from .solver import METHODS, fingerprint, solve

STOCHASTIC = {"B3", "LNS", "ALNS", "VNS", "ALNS_NO_SCHEDULE", "ALNS_NO_2OPT"}


def _instance_stem(name):
    """Keep ordinary legacy names; encode display names unsafe on Windows/POSIX."""
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved |= {f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)}
    if (re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", name)
            and not name.endswith(".") and name.split(".")[0].upper() not in reserved):
        return name
    return "case-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:24]


def _file_identity(info):
    identity = (info.st_dev, info.st_ino) if info.st_ino else ()
    birth = getattr(info, "st_birthtime_ns", None)
    if birth is None and os.name == "nt":
        birth = info.st_ctime_ns
    return identity + (birth,) if birth is not None else identity


def _seal_file(path):
    info = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode):
        raise InputError(f"Benchmark evidence is not a regular file: {path}")
    return path, _file_identity(info), hashlib.sha256(path.read_bytes()).hexdigest()


class _OutputGuard:
    def __init__(self, output):
        self.directories = {path: _file_identity(path.stat(follow_symlinks=False))
                            for path in (output, output / "raw", output / "instances")}
        self.headers = [_seal_file(output / name) for name in ("config.json", "preregistered.json")]

    def check(self, *files):
        path = None
        try:
            for path, expected in self.directories.items():
                info = path.stat(follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode) or _file_identity(info) != expected:
                    raise InputError(f"Benchmark output directory was replaced: {path}")
            for path, identity, digest in (*self.headers, *files):
                if _seal_file(path)[1:] != (identity, digest):
                    raise InputError(f"Benchmark evidence changed during execution: {path}")
        except OSError as exc:
            raise InputError(f"Benchmark evidence disappeared during execution: {path}; "
                             "refusing to recreate missing evidence") from exc


def _write_evidence_json(path, data):
    # Parent directories are sealed; never recreate them after external loss.
    content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(content)


def benchmark(config, output, progress=None):
    output = Path(output).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise InputError("Benchmark requires a new or empty directory; refusing to overwrite evidence")
    methods = config.get("methods", ["B0", "B2", "LNS", "ALNS", "VNS"])
    if not methods or "B0" not in methods or len(methods) != len(set(methods)) or any(m not in METHODS for m in methods):
        raise InputError("Benchmark methods must be unique, supported and include B0")
    sizes = config.get("sizes", [20, 50])
    instance_seeds = config.get("instance_seeds", [101])
    search_seeds = config.get("search_seeds", [7])
    if any(not values or len(values) != len(set(values)) for values in (sizes, instance_seeds, search_seeds)):
        raise InputError("Sizes and seed lists must be nonempty and unique")
    options = SearchConfig(**config.get("search", {})).validate()
    if "run_order_seed" in config and type(config["run_order_seed"]) is not int:
        raise InputError("run_order_seed must be an integer")
    started = time.perf_counter()
    rows, runs = [], []
    source_hashes = python_source_hashes(Path(__file__).parent)
    instance_paths = config.get("instances", [])
    scenario_keys = config.get("scenarios", [])
    if instance_paths and scenario_keys:
        raise InputError("Benchmark cannot combine instances and scenarios")
    if "inline_instances" in config:
        if (not isinstance(config["inline_instances"], list) or not config["inline_instances"]
                or instance_paths or scenario_keys):
            raise InputError("inline_instances must be a nonempty exclusive input inventory")
        datasets = [(Instance.from_dict(data), None) for data in config["inline_instances"]]
    elif instance_paths:
        datasets = [(read_instance(path), None) for path in instance_paths]
    elif scenario_keys:
        if not isinstance(scenario_keys, list) or not scenario_keys:
            raise InputError("scenarios must be a nonempty list")
        unknown = sorted(set(scenario_keys) - set(MAP_SCENARIOS))
        if unknown:
            raise InputError(f"Unknown benchmark scenarios: {unknown}")
        scenario_seeds = config.get("scenario_seeds", [42])
        if not scenario_seeds or len(scenario_seeds) != len(set(scenario_seeds)):
            raise InputError("scenario_seeds must be nonempty and unique")
        overrides = config.get("scenario_overrides", {})
        if not isinstance(overrides, dict):
            raise InputError("scenario_overrides must be an object")
        datasets = [
            (generate_scenario(scenario, seed=seed, **overrides.get(scenario, {})), seed)
            for scenario in scenario_keys
            for seed in scenario_seeds
        ]
    else:
        datasets = [(generate(n=n, seed=s, **config.get("generator", {})), s) for n in sizes for s in instance_seeds]
    names = [instance.name.casefold() for instance, _ in datasets]
    if len(names) != len(set(names)):
        raise InputError("Benchmark instance names must be unique (case-insensitive) to avoid overwriting results")
    stems = {instance.name: _instance_stem(instance.name) for instance, _ in datasets}
    if len({value.casefold() for value in stems.values()}) != len(stems):
        raise InputError("Benchmark instance names must produce unique filenames")
    instance_files = {name: f"instances/{stem}.json" for name, stem in stems.items()}
    write_json(output / "config.json", config)
    # Seal input identities before evaluating any method on them.
    write_json(output / "preregistered.json", {
        "config": config, "source_sha256": source_hashes, "source_inventory_version": 2,
        "instances": {instance.name: fingerprint(instance) for instance, _ in datasets}})
    (output / "raw").mkdir()
    (output / "instances").mkdir()
    guard = _OutputGuard(output)
    saved_files = []
    for instance, instance_seed in datasets:
        guard.check()
        instance_path = output / instance_files[instance.name]
        if instance_path.resolve().parent != (output / "instances").resolve():
            raise InputError("Benchmark instance path escapes its output directory")
        _write_evidence_json(instance_path, instance.to_dict())
        saved_files.append(_seal_file(instance_path))
    input_seals = {seal[0].stem: seal for seal in saved_files}
    tasks = [(instance, instance_seed, method, seed)
             for instance, instance_seed in datasets for method in methods
             for seed in (search_seeds if method in STOCHASTIC else search_seeds[:1])]
    if "run_order_seed" in config:
        random.Random(config["run_order_seed"]).shuffle(tasks)
    for instance, instance_seed, method, seed in tasks:
        instance_seal = input_seals[stems[instance.name]]
        guard.check(instance_seal)
        result = solve(instance, method, seed, options, tuple(config.get("weights", [1/3, 1/3, 1/3])))
        guard.check(instance_seal)
        file_name = f"{stems[instance.name]}-{method}-seed{seed}.json"
        result_path = output / "raw" / file_name
        if result_path.resolve().parent != (output / "raw").resolve():
            raise InputError("Benchmark result path escapes its output directory")
        _write_evidence_json(result_path, result)
        result_seal = _seal_file(result_path)
        saved_files.append(result_seal)
        row = {"instance": instance.name, "n": len(instance.orders), "instance_seed": instance_seed,
               "method": method, "search_seed": seed, "feasible": result["feasible"],
               **result["metrics"], **result["timing"],
               **{key: result["search"][key] for key in ("iterations_completed", "stop_reason",
                  "adaptation_updates", "adapted_iterations", "search_executed", "budget_scope")}}
        rows.append(row)
        runs.append({"file": f"raw/{file_name}", "instance_sha256": result["instance_sha256"]})
        if progress:
            progress(row)
        guard.check(instance_seal, result_seal)
    # The complete inventory is checked only at completion, keeping run guards linear.
    guard.check(*saved_files)
    with (output / "runs.csv").open("x", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["instance"], row["method"])].append(row)
    summaries = []
    metric_names = ("objective", "distance", "makespan", "tardiness", "late_orders", "on_time_rate", "total_seconds")
    for (name, method), group in sorted(grouped.items()):
        baseline = grouped[(name, "B0")][0]
        summary = {"instance": name, "method": method, "runs": len(group), "feasible_rate": sum(row["feasible"] for row in group) / len(group)}
        summary["search_diagnostics"] = {
            "zero_iteration_runs": sum(r["iterations_completed"] == 0 for r in group) if method in STOCHASTIC else None,
            "iterations_min": min(r["iterations_completed"] for r in group),
            "iterations_median": statistics.median(r["iterations_completed"] for r in group),
            "adapted_runs": sum(r["adapted_iterations"] > 0 for r in group),
            "initialization_mean_seconds": statistics.mean(r["initialization_seconds"] for r in group),
            "search_mean_seconds": statistics.mean(r["search_seconds"] for r in group),
            "stop_reasons": {reason: sum(r["stop_reason"] == reason for r in group) for reason in sorted({r["stop_reason"] for r in group})}}
        for metric in metric_names:
            values = [r[metric] for r in group]
            avg = statistics.mean(values)
            sign = 1 if metric == "on_time_rate" else -1
            summary[metric] = {"mean": avg, "median": statistics.median(values), "std": statistics.stdev(values) if len(values) > 1 else 0., "best": max(values) if sign == 1 else min(values), "difference_vs_B0": avg - baseline[metric], "improvement_pct_vs_B0": 100 * sign * (avg - baseline[metric]) / baseline[metric] if baseline[metric] else None}
        summaries.append(summary)
    guard.check()
    _write_evidence_json(output / "summary.json", summaries)
    comparisons = paired_comparisons(rows, tuple(config.get("references", ["B0", "B2", "B3", "LNS", "VNS"])))
    guard.check()
    _write_evidence_json(output / "comparison.json", comparisons)
    guard.check()
    _write_evidence_json(output / "manifest.json", {"config": config, "source_sha256": source_hashes,
        "source_inventory_version": 2, "instance_files": instance_files,
        "python": platform.python_version(), "platform": platform.platform(), "cpu": platform.processor(),
        "elapsed_seconds": time.perf_counter() - started, "runs": runs})
    lines = ["# Kết quả benchmark", "", "Dữ liệu tổng hợp; kết quả đo từ các lần chạy trong thư mục raw. Mỗi hàng tổng hợp seed trên cùng một instance, không coi seed là các instance độc lập.", "", "| Instance | Method | Runs | F mean ± std | Distance mean (m) | Makespan mean (min) | Tardiness mean (min) | Late mean | On-time rate | Total mean (s) | ΔF vs B0 (%) |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    if config.get("instances"):
        lines[2] = "Dữ liệu từ file cấu hình; giữ đơn vị nguồn và mục tiêu hạn mềm của project. Không so với best-known của bài toán gốc. Tổng hợp seed trong từng instance."
        lines[4] = lines[4].replace("(m)", "(instance units)").replace("(min)", "(instance units)")
    for row in summaries:
        f = row["objective"]
        improvement = "N/A" if f["improvement_pct_vs_B0"] is None else f"{f['improvement_pct_vs_B0']:.2f}"
        values = [row[m]["mean"] for m in metric_names[1:]]
        lines.append(f"| {row['instance']} | {row['method']} | {row['runs']} | {f['mean']:.5f} ± {f['std']:.5f} | " + " | ".join(f"{v:.3f}" for v in values) + f" | {improvement} |")
    lines += ["", f"Tất cả {len(rows)} nghiệm đã qua validator độc lập trước khi xuất.", "", "ΔF dương = cải thiện, âm = suy giảm. Thời gian tổng gồm graph/reference B0, khởi tạo và search. Ngân sách search tính cả khởi tạo, được kiểm tra giữa các thao tác; một phép tính đang chạy có thể vượt nhẹ giới hạn. Các method dùng cùng cấu hình search, heuristic dừng khi hoàn thành.", "", "Đây là báo cáo cho đúng cấu hình đã lưu, chưa phải bằng chứng tổng quát ALNS tốt hơn trên mọi dữ liệu.", ""]
    lines += ["## So sánh theo instance", "",
              ("Lấy trung bình seed trong từng instance trước; mỗi instance có một phiếu. "
              "Thắng/hòa/thua theo F với sai số tuyệt đối 1e-9. Không phải kiểm định ý nghĩa thống kê. "
              "Phần trăm cải thiện bỏ các mẫu có F tham chiếu bằng 0."), "",
              "| Method | Reference | Instances | Win | Tie | Loss | Mean improvement (%) |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for pair in comparisons:
        improvement = pair["mean_improvement_pct"]
        label = "N/A" if improvement is None else f"{improvement:.3f}"
        lines.append(f"| {pair['method']} | {pair['reference']} | {pair['instances']} | "
                     f"{pair['win']} | {pair['tie']} | {pair['loss']} | {label} |")
    lines += ["", "## Hoạt động tìm kiếm", "",
              ("Không loại ca 0 vòng khỏi bảng điểm để tránh thiên lệch chọn mẫu. Ca đó chỉ phản ánh khởi tạo; "
              "không dùng để khẳng định lợi ích search. Adapted runs đếm ca có vòng hoàn thành sau cập nhật trọng số. "
              "Một cập nhật ở cuối lần chạy chưa chứng minh trọng số đã được dùng. Median các chỉ số có trong summary.json."), "",
              "| Instance | Method | Zero-iteration runs | Min / median iterations | Adapted runs | Init mean (s) | Search mean (s) |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for row in summaries:
        if row["method"] not in STOCHASTIC:
            continue
        diag = row["search_diagnostics"]
        lines.append(f"| {row['instance']} | {row['method']} | {diag['zero_iteration_runs']} | "
                     f"{diag['iterations_min']} / {diag['iterations_median']} | {diag['adapted_runs']} | "
                     f"{diag['initialization_mean_seconds']:.4f} | {diag['search_mean_seconds']:.4f} |")
    guard.check()
    with (output / "REPORT.md").open("x", encoding="utf-8") as file:
        file.write("\n".join(lines))
    guard.check(*saved_files)
    return rows

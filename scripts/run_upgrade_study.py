"""Locked development/holdout study. Run sequentially; never overwrite completed evidence."""
import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generator import generate
from src.models import read_instance
from src.provenance import python_source_hashes
from src.search import SearchConfig, canonical_search_config
from src.solver import fingerprint, solve
from src.validator import validate_solution


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def create(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation makes interruption visible instead of silently replacing a run.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def sources():
    values = {"src/"+name: value for name, value in python_source_hashes(ROOT / "src").items()}
    values["scripts/run_upgrade_study.py"] = digest(Path(__file__))
    return values


def configs(seconds):
    base = SearchConfig(iterations=100000, seconds=seconds, segment=10)
    choices = {}
    for method in ("ALNS", "LNS"):
        for policy in ("uniform", "guided"):
            for cached in (False, True):
                label = f"{method}_{policy}_{'incremental' if cached else 'full'}"
                choices[label] = {"method": method, "config": asdict(replace(base,
                    candidate_policy=policy, incremental_validation=cached))}
    for cached in (False, True):
        for trials in (4, 8):
            label = f"VNS_{'incremental' if cached else 'full'}_local{trials}"
            choices[label] = {"method": "VNS", "config": asdict(replace(base,
                incremental_validation=cached, local_trials=trials))}
    return choices


def schedule(cases, seeds, choices, shuffle_seed):
    rng = random.Random(shuffle_seed)
    blocks = [(case["name"], seed) for case in cases for seed in seeds]
    rng.shuffle(blocks)
    rows = []
    for name, seed in blocks:
        labels = sorted(choices)
        rng.shuffle(labels)
        for label in labels:
            rows.append({"case": name, "seed": seed, "variant": label})
    return rows


def prepare(output):
    protocol_path = output / "protocol.lock.json"
    if protocol_path.exists():
        raise RuntimeError("Protocol already exists; use run/verify or a new output directory")
    output.mkdir(parents=True, exist_ok=True)
    cases = {"pilot": [], "holdout": []}
    for stage, repetitions, start_seed in (("pilot", 1, 410001), ("holdout", 3, 510001)):
        index = 0
        for n in (20, 100, 200):
            for layout, aisles, rows, cross in (("single", 5, 6, 0), ("double", 6, 8, 1)):
                for tightness in (.08, .35):
                    for repetition in range(repetitions):
                        generation_seed = start_seed + index
                        name = f"{stage}-n{n}-{layout}-t{int(tightness*100):02d}-r{repetition+1}"
                        instance = replace(generate(n=n, seed=generation_seed, pickers=3,
                            capacity=30, aisles=aisles, rows=rows, cross_aisles=cross,
                            tightness=tightness), name=name)
                        relative = f"inputs/{name}.json"
                        create(output / relative, instance.to_dict())
                        cases[stage].append({"name": name, "n": n, "layout": layout,
                            "tightness": tightness, "replication": repetition+1,
                            "generation_seed": generation_seed, "path": relative,
                            "file_sha256": digest(output / relative), "instance_sha256": fingerprint(instance)})
                        index += 1
    source = sources()
    for relative in source:
        destination = output / "source" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    pilot_choices = configs(1.5)
    # Configurations are selected using only development cases, before holdout is opened.
    protocol = {"schema_version": 1, "created_utc": now(), "source_sha256": source,
        "cases": cases, "pilot_variants": pilot_choices,
        "pilot_search_seeds": [411, 419, 431],
        "holdout_search_seeds": [503, 509, 521, 523, 541, 547, 557, 563, 569, 571],
        "holdout_seconds": 3., "weights": [1/3, 1/3, 1/3],
        "selection": {"criterion": "minimum mean per-instance mean objective on n=100/200 pilot cases",
            "candidates_per_method": 4, "tie_rule": "lexicographic label for difference <= 1e-12",
            "same_budget_seconds": 1.5},
        "primary": {"contrast": "ALNS_SELECTED vs ALNS_OLD", "unit": "independently generated instance",
            "cases": "n=100/200 (24 instances)", "effect": "100*(mean_F_old-mean_F_selected)/mean_F_old",
            "engineering_threshold_percent": 1.,
            "uncertainty": "paired two-stage bootstrap: instances within 8 design strata, seed pairs within each drawn instance",
            "bootstrap_replicates": 10000, "bootstrap_seed": 610019,
            "interval": "percentile 95%, conditional on chosen synthetic generator; not simultaneous"},
        "secondary": ["n=20", "comparisons with tuned LNS/VNS and B0/B2",
            "pilot factorial ablation (exploratory)", "timing, evaluations, iterations and adaptive use",
            "best-objective traces under initialization+search budget"],
        "execution": "single solver process; shuffled instance/seed blocks and variants within each block; no concurrent pytest/profile",
        "budget_scope": "initialization_and_search; preprocessing and final validation outside; cooperative deadline",
        "pilot_schedule": schedule(cases["pilot"], [411, 419, 431], pilot_choices, 610021),
        "baseline_behavior": "uniform/full unchanged; legacy fixed-iteration plan SHA256 6847ff79483581bbc201704dc9d34bbfd08d494be8a36305db40d4e0a1498e3d"}
    create(protocol_path, protocol)
    create(output / "protocol.sha256.json", {"protocol_sha256": digest(protocol_path)})
    print(f"Prepared {len(cases['pilot'])} pilot and {len(cases['holdout'])} holdout inputs; source frozen", flush=True)


def locked(output, require_current=True):
    path = output / "protocol.lock.json"
    if read(output / "protocol.sha256.json")["protocol_sha256"] != digest(path):
        raise RuntimeError("Protocol hash mismatch")
    protocol = read(path)
    if require_current and protocol["source_sha256"] != sources():
        raise RuntimeError("Study source changed after protocol lock")
    for name, expected in protocol["source_sha256"].items():
        if digest(output / "source" / name) != expected:
            raise RuntimeError("Archived source hash mismatch: " + name)
    for case in protocol["cases"]["pilot"] + protocol["cases"]["holdout"]:
        if digest(output / case["path"]) != case["file_sha256"]:
            raise RuntimeError("Input hash mismatch: " + case["name"])
    return protocol


def audit(result, instance, variant, seed, baseline):
    errors = validate_solution(instance, result)
    if errors:
        raise RuntimeError("; ".join(errors))
    if result["method"] != variant["method"] or result["search"]["seed"] != seed:
        raise RuntimeError("Method/seed mismatch")
    if result["instance_sha256"] != fingerprint(instance):
        raise RuntimeError("Input fingerprint mismatch")
    if canonical_search_config(result["search"]["config"]) != canonical_search_config(variant["config"]):
        raise RuntimeError("Search configuration mismatch")
    if result["objective_config"] != baseline["objective_config"]:
        raise RuntimeError("Objective is not anchored to audited B0")
    if any(not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0
           for v in result["timing"].values()):
        raise RuntimeError("Invalid timing")
    trace = result["search"].get("trace", [])
    if any(b["objective"] > a["objective"] + 1e-10 for a, b in zip(trace, trace[1:])):
        raise RuntimeError("Best objective trace increased")


def run_one(output, stage, case, variant_name, variant, seed, baseline, session):
    path = output / "raw" / stage / f"{case['name']}__{variant_name}__s{seed}.json"
    instance = read_instance(output / case["path"])
    if path.exists():
        wrapper = read(path)
    else:
        started = now()
        result = solve(instance, variant["method"], seed, SearchConfig(**variant["config"]))
        wrapper = {"case": case["name"], "variant": variant_name, "seed": seed,
            "session": session, "started_utc": started, "finished_utc": now(),
            "protocol_sha256": digest(output / "protocol.lock.json"), "result": result}
        audit(result, instance, variant, seed, baseline or result)
        create(path, wrapper)
    if (wrapper["case"], wrapper["variant"], wrapper["seed"]) != (case["name"], variant_name, seed):
        raise RuntimeError("Run identity mismatch")
    if wrapper["protocol_sha256"] != digest(output / "protocol.lock.json"):
        raise RuntimeError("Run protocol mismatch")
    audit(wrapper["result"], instance, variant, seed, baseline or wrapper["result"])
    return wrapper["result"]


def selection(output, protocol):
    path = output / "selection.lock.json"
    if path.exists():
        value = read(path)
        if digest(path) != read(output / "selection.sha256.json")["selection_sha256"]:
            raise RuntimeError("Selection hash mismatch")
        return value
    scores = {}
    large = [case for case in protocol["cases"]["pilot"] if case["n"] >= 100]
    for label in sorted(protocol["pilot_variants"]):
        per_case = []
        for case in large:
            values = [read(output / "raw" / "pilot" / f"{case['name']}__{label}__s{seed}.json")["result"]["metrics"]["objective"]
                      for seed in protocol["pilot_search_seeds"]]
            per_case.append(sum(values)/len(values))
        scores[label] = sum(per_case)/len(per_case)
    selected = {}
    for method in ("ALNS", "LNS", "VNS"):
        candidates = sorted(k for k in scores if k.startswith(method+"_"))
        best = min(scores[k] for k in candidates)
        selected[method] = next(k for k in candidates if scores[k] <= best+1e-12)
    base = asdict(SearchConfig(iterations=100000, seconds=3., segment=10))
    choices = {"ALNS_OLD": {"method": "ALNS", "config": base}}
    for label, method in (("ALNS_SELECTED", "ALNS"), ("LNS_TUNED", "LNS"), ("VNS_TUNED", "VNS")):
        choice = json.loads(json.dumps(protocol["pilot_variants"][selected[method]]))
        choice["config"]["seconds"] = protocol["holdout_seconds"]
        choices[label] = choice
    value = {"locked_utc": now(), "protocol_sha256": digest(output / "protocol.lock.json"),
        "scores": scores, "selected": selected, "holdout_variants": choices,
        "holdout_schedule": schedule(protocol["cases"]["holdout"], protocol["holdout_search_seeds"], choices, 610027)}
    create(path, value)
    create(output / "selection.sha256.json", {"selection_sha256": digest(path)})
    print("Locked pilot selection: " + json.dumps(selected), flush=True)
    return value


def run_stage(output, stage):
    protocol = locked(output)
    if stage == "holdout" and not (output / "pilot.verified.json").exists():
        raise RuntimeError("Pilot must be complete and verified before holdout")
    selected = selection(output, protocol) if stage == "holdout" else None
    variants = selected["holdout_variants"] if selected else protocol["pilot_variants"]
    jobs = selected["holdout_schedule"] if selected else protocol["pilot_schedule"]
    session = now().replace(":", "-")
    create(output / "sessions" / f"{stage}-{session}.json", {"stage": stage, "started_utc": now(),
        "protocol_sha256": digest(output / "protocol.lock.json"), "source_sha256": sources()})
    cases = {case["name"]: case for case in protocol["cases"][stage]}
    base_config = asdict(SearchConfig(iterations=100000, seconds=0, segment=10))
    baselines = {}
    for case in cases.values():
        b0 = run_one(output, stage, case, "B0", {"method": "B0", "config": base_config}, 0, None, session)
        baselines[case["name"]] = b0
        run_one(output, stage, case, "B2", {"method": "B2", "config": base_config}, 0, b0, session)
    for index, job in enumerate(jobs, 1):
        if sources() != protocol["source_sha256"]:
            raise RuntimeError("Source changed during execution")
        result = run_one(output, stage, cases[job["case"]], job["variant"], variants[job["variant"]],
            job["seed"], baselines[job["case"]], session)
        if index % 12 == 0 or index == len(jobs):
            print(f"{stage} {index}/{len(jobs)}: {job['variant']}, F={result['metrics']['objective']:.6f}", flush=True)
    if stage == "pilot":
        selection(output, protocol)
    verify(output, stage)


def verify(output, stage):
    protocol = locked(output, require_current=False)
    variants = (selection(output, protocol)["holdout_variants"] if stage == "holdout"
                else protocol["pilot_variants"])
    seeds = protocol[f"{stage}_search_seeds"]
    baseline_config = asdict(SearchConfig(iterations=100000, seconds=0, segment=10))
    hashes = {}
    for case in protocol["cases"][stage]:
        instance = read_instance(output / case["path"])
        # Recompute B0 reference independently of the saved declarations.
        expected_b0 = solve(instance, "B0", 0, SearchConfig(**baseline_config))
        for label, variant, run_seeds in [("B0", {"method": "B0", "config": baseline_config}, [0]),
            ("B2", {"method": "B2", "config": baseline_config}, [0]),
            *((label, variant, seeds) for label, variant in variants.items())]:
            for seed in run_seeds:
                path = output / "raw" / stage / f"{case['name']}__{label}__s{seed}.json"
                wrapper = read(path)
                if (wrapper["case"], wrapper["variant"], wrapper["seed"]) != (case["name"], label, seed):
                    raise RuntimeError("Run identity mismatch")
                if wrapper["protocol_sha256"] != digest(output / "protocol.lock.json"):
                    raise RuntimeError("Run protocol mismatch")
                audit(wrapper["result"], instance, variant, seed, expected_b0)
                hashes[path.relative_to(output).as_posix()] = digest(path)
    path = output / f"{stage}.verified.json"
    value = {"count": len(hashes), "protocol_sha256": digest(output / "protocol.lock.json"), "raw_sha256": hashes}
    if path.exists():
        if read(path) != value:
            raise RuntimeError("Completed run inventory changed")
    else:
        create(path, value)
    print(f"Verified {stage}: {len(hashes)} complete, feasible, B0-anchored runs", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "pilot", "holdout", "verify"))
    parser.add_argument("--output", type=Path, default=ROOT / "results/high_score_upgrade_20261010")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.output)
    elif args.action == "verify":
        verify(args.output, "pilot")
        verify(args.output, "holdout")
    else:
        run_stage(args.output, args.action)

"""Instrument fixed-iteration search; these timings are diagnostics, not benchmark rankings."""
import argparse
import cProfile
from dataclasses import asdict
from pathlib import Path
import pstats
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.generator import generate
from src.models import write_json
from src.provenance import python_source_hashes
from src.search import SearchConfig
from src.solver import fingerprint, solve


def run(output):
    output.mkdir(parents=True, exist_ok=False)
    config = SearchConfig(seconds=0, iterations=10, candidate_limit=24, segment=5)
    rows = []
    for n in (20, 100, 200):
        instance = generate(n=n, seed=27100+n, capacity=30, tightness=.15)
        write_json(output / f"input-n{n}.json", instance.to_dict())
        profiler = cProfile.Profile()
        started = time.perf_counter()
        result = profiler.runcall(solve, instance, "ALNS", 271, config)
        elapsed = time.perf_counter() - started
        profiler.dump_stats(str(output / f"n{n}.prof"))
        stats = pstats.Stats(profiler)
        functions = []
        for (filename, line, name), (primitive, calls, own, cumulative, _) in stats.stats.items():
            if name in {"greedy", "destroy", "repair", "insertion_options", "cost", "check_plan",
                        "batch_info", "route", "freeze", "mutable", "_dijkstra"}:
                functions.append({"function": name, "calls": calls, "primitive_calls": primitive,
                                  "own_seconds": own, "cumulative_seconds": cumulative})
        row = {"n": n, "instance_sha256": fingerprint(instance), "instrumented_seconds": elapsed,
               "cost_evaluations": result["search"]["cost_evaluations"],
               "iterations_completed": result["search"]["iterations_completed"],
               "timing": result["timing"], "functions": sorted(functions, key=lambda r: -r["cumulative_seconds"])}
        rows.append(row)
        write_json(output / f"result-n{n}.json", result)
        print(f"n={n}: {elapsed:.3f}s; {row['cost_evaluations']} cost evaluations", flush=True)
    write_json(output / "summary.json", {"scope": "fixed-iteration cProfile diagnostic; cumulative times overlap",
        "config": asdict(config), "source_sha256": python_source_hashes(ROOT / "src"), "rows": rows})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)

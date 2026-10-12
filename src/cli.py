import argparse
import json
from pathlib import Path

from .benchmark import benchmark
from .exact import solve_exact
from .experiment import dry_run, export_report, is_experiment_config, run_experiment
from .generator import MAP_SCENARIOS, generate, generate_scenario
from .models import InputError, read_instance, write_json
from .objectives import WEIGHT_PROFILES, profile_weights
from .search import SearchConfig
from .solver import METHODS, solve
from .validator import validate_solution


def _print_report_files(output, charts, exported=None):
    output = Path(output).resolve()
    if not charts:
        print(f"Charts disabled; CSV tables and evaluation.json exported to {output}")
        return
    availability = (exported["availability"] if exported is not None else
                    json.loads((output / "availability.json").read_text(encoding="utf-8")))
    png_count = sum("png" in entry["files"]
                    for style in ("report", "presentation") for entry in availability[style])
    print(f"Exported {png_count} PNG figures")
    print(f"Open offline gallery: {output / 'index.html'}")


def _print_plan(planned):
    if planned.get("sensitivity_runs", 0):
        print(f"Preset {planned['preset']}: {planned['primary_instances']} primary instances + "
              f"{planned['sensitivity_cases']} sensitivity input-condition cases, "
              f"{planned['runs']} solver runs", flush=True)
        print(f"Configured search budgets: {planned['search_budget_seconds'] / 60:.1f} minutes "
              "(not a measured wall-clock estimate)", flush=True)
    else:
        print(f"Preset {planned['preset']}: {planned['instances']} instances, "
              f"{planned['runs']} solver runs", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Warehouse batching + routing + picker scheduling")
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="Generate a reproducible synthetic instance")
    gen.add_argument("--scenario", choices=list(MAP_SCENARIOS.keys()), default=None,
                     help="Predefined warehouse scenario (single_block, double_block, mega_hub, rush_hour, abc_zonal)")
    gen.add_argument("--orders", type=int, default=None)
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--pickers", type=int, default=None)
    gen.add_argument("--capacity", type=float, default=None)
    gen.add_argument("--aisles", type=int, default=None)
    gen.add_argument("--rows", type=int, default=None)
    gen.add_argument("--tightness", type=float, default=None)
    gen.add_argument("--output", required=True)
    run = sub.add_parser("solve", help="Optimize a schema-v1 JSON instance")
    run.add_argument("instance")
    run.add_argument("--method", choices=METHODS, default="ALNS")
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--seconds", type=float, default=3.)
    run.add_argument("--iterations", type=int, default=200)
    run.add_argument("--candidate-limit", type=int, default=24)
    run.add_argument("--candidate-policy", choices=("uniform", "guided"), default="uniform")
    run.add_argument("--incremental-validation", action="store_true")
    objective = run.add_mutually_exclusive_group()
    objective.add_argument("--weights", type=float, nargs=3, metavar=("DISTANCE", "MAKESPAN", "TARDINESS"))
    objective.add_argument("--profile", choices=list(WEIGHT_PROFILES), default="balanced")
    run.add_argument("--output", required=True)
    validate = sub.add_parser("validate", help="Independently validate exported solution")
    validate.add_argument("instance")
    validate.add_argument("solution")
    exact = sub.add_parser("exact", help="Full enumeration for tiny instances")
    exact.add_argument("instance")
    exact.add_argument("--seconds", type=float, default=30.)
    exact.add_argument("--max-states", type=int, default=200000)
    exact_objective = exact.add_mutually_exclusive_group()
    exact_objective.add_argument("--weights", type=float, nargs=3, metavar=("DISTANCE", "MAKESPAN", "TARDINESS"))
    exact_objective.add_argument("--profile", choices=list(WEIGHT_PROFILES), default="balanced")
    exact.add_argument("--output", required=True)
    bench = sub.add_parser("benchmark", help="Run an audited experiment and export tables and figures")
    bench.add_argument("--config", default="configs/benchmark.json")
    bench.add_argument("--preset", choices=("quick", "report"), default=None)
    bench.add_argument("--output", help="New evidence directory (default: results/benchmark_<preset>)")
    bench.add_argument("--groups", nargs="+", help="Select named experiment groups; all selected inputs are required")
    bench.add_argument("--dry-run", action="store_true", help="Validate selected inputs and show counts without writing or solving")
    bench.add_argument("--resume", action="store_true", help="Reuse audited complete groups; preserve and restart interrupted group attempts")
    bench.add_argument("--presentation", action="store_true", help="Also export PNG figures for slides")
    bench.add_argument("--no-charts", action="store_true", help="Export audited tables and JSON without rendering figures")
    report = sub.add_parser("report", help="Audit saved evidence and export a new report without running solvers")
    report.add_argument("--input", required=True, help="Experiment, low-level benchmark directory or evaluation.json")
    report.add_argument("--output", required=True, help="New report output directory")
    report.add_argument("--presentation", action="store_true", help="Also export PNG figures for slides")
    report.add_argument("--no-charts", action="store_true", help="Export audited tables and JSON without rendering figures")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            if args.scenario:
                overrides = {}
                if args.orders is not None:
                    overrides["n"] = args.orders
                if args.pickers is not None:
                    overrides["pickers"] = args.pickers
                if args.capacity is not None:
                    overrides["capacity"] = args.capacity
                if args.aisles is not None:
                    overrides["aisles"] = args.aisles
                if args.rows is not None:
                    overrides["rows"] = args.rows
                if args.tightness is not None:
                    overrides["tightness"] = args.tightness
                instance = generate_scenario(args.scenario, seed=args.seed, **overrides)
            else:
                orders = 30 if args.orders is None else args.orders
                pickers = 3 if args.pickers is None else args.pickers
                capacity = 30. if args.capacity is None else args.capacity
                aisles = 5 if args.aisles is None else args.aisles
                rows = 6 if args.rows is None else args.rows
                tightness = .25 if args.tightness is None else args.tightness
                instance = generate(orders, args.seed, pickers, capacity, aisles, rows, tightness)
            write_json(args.output, instance.to_dict())
            print(f"Generated {instance.name}: {len(instance.orders)} orders -> {args.output}")
        elif args.command == "solve":
            config = SearchConfig(seconds=args.seconds, iterations=args.iterations, candidate_limit=args.candidate_limit,
                                  candidate_policy=args.candidate_policy,
                                  incremental_validation=args.incremental_validation)
            weights = args.weights if args.weights is not None else profile_weights(args.profile)
            result = solve(read_instance(args.instance), args.method, args.seed, config, weights)
            write_json(args.output, result)
            print(json.dumps(result["metrics"], indent=2))
            print(f"Validated solution -> {args.output}")
        elif args.command == "validate":
            result = json.loads(Path(args.solution).read_text(encoding="utf-8"))
            errors = validate_solution(read_instance(args.instance), result)
            if errors:
                raise InputError("; ".join(errors))
            print("VALID: orders, capacity, physical paths, timing and metrics")
        elif args.command == "exact":
            weights = args.weights if args.weights is not None else profile_weights(args.profile)
            result = solve_exact(read_instance(args.instance), args.seconds, args.max_states, weights)
            write_json(args.output, result)
            print(f"Certified optimal: {result['certified_optimal']}; evaluated states: {result['states']}")
        elif args.command == "report":
            exported = export_report(args.input, args.output, presentation=args.presentation, charts=not args.no_charts)
            print(f"Audited report exported to {args.output}")
            _print_report_files(args.output, not args.no_charts, exported)
        elif args.command == "benchmark":
            config = json.loads(Path(args.config).read_text(encoding="utf-8"))
            if args.output is None:
                label = f"benchmark_{args.preset or 'quick'}" if is_experiment_config(config) else Path(args.config).stem
                args.output = str(Path("results") / label)
            if args.dry_run:
                planned = dry_run(config, args.preset or "quick", args.config, args.groups)
                _print_plan(planned)
                for group in planned["groups"]:
                    print(f"  {group['name']}: {group['instances']} instances, {group['runs']} runs")
                for skipped in planned["skipped_groups"]:
                    print(f"  Skipped {skipped['name']}: {skipped['reason']}")
                print(f"Purpose: {planned['purpose']}; no files written and no solvers run")
            elif is_experiment_config(config):
                planned = dry_run(config, args.preset or "quick", args.config, args.groups)
                _print_plan(planned)
                for skipped in planned["skipped_groups"]:
                    print(f"Skipped {skipped['name']}: {skipped['reason']}", flush=True)
                payload = run_experiment(config, args.output, args.preset or "quick", args.config,
                                         groups=args.groups, resume=args.resume,
                                         presentation=args.presentation, charts=not args.no_charts,
                                         progress=lambda row: print(
                                             f"{row['group']} {row['instance']} {row['method']} "
                                             f"seed={row['search_seed']} F={row['objective']:.5f}", flush=True))
                runs = sum(len(g["results"]) for g in payload["groups"])
                print(f"Saved {runs} audited runs and report to {args.output}")
                _print_report_files(Path(args.output) / "report", not args.no_charts)
            else:
                if args.resume or args.groups or args.preset:
                    raise InputError("--resume, --groups and --preset require a unified experiment config")
                rows = benchmark(config, args.output)
                exported = export_report(args.output, Path(args.output) / "report",
                                         presentation=args.presentation, charts=not args.no_charts)
                print(f"Saved {len(rows)} audited runs and report to {args.output}")
                _print_report_files(Path(args.output) / "report", not args.no_charts, exported)
    except (InputError, OSError, json.JSONDecodeError, TypeError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()

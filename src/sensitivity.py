"""Locked, paired exploratory conditions for time and objective-weight sensitivity."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
import random

from .benchmark import STOCHASTIC
from .models import InputError, Instance
from .objectives import profile_weights
from .search import SearchConfig
from .solver import fingerprint


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()


def expand_conditions(groups, settings, preset, datasets_for):
    """Choose inputs from identity alone and declare every condition before runs."""
    if not isinstance(settings, dict):
        raise InputError("sensitivity must be an object")
    settings = deepcopy(settings)
    overrides = settings.pop("presets", {})
    if not isinstance(overrides, dict) or not isinstance(overrides.get(preset, {}), dict):
        raise InputError("sensitivity presets must contain objects")
    settings.update(overrides.get(preset, {}))
    if type(settings.get("enabled", True)) is not bool:
        raise InputError("sensitivity enabled must be boolean")
    if settings.get("enabled", True) is False:
        return []
    limit = settings.get("instances_per_group", 3)
    seeds = settings.get("search_seeds", [1, 2, 3, 4, 5])
    budgets = settings.get("time_budgets", [.5, 3., 6.])
    weight_seconds = settings.get("weight_seconds", 3.)
    profiles = settings.get("weight_profiles", ["balanced", "distance", "tardiness"])
    order_seed = settings.get("schedule_seed", 20261011)
    if type(limit) is not int or not 1 <= limit <= 3 or type(order_seed) is not int:
        raise InputError("sensitivity needs 1–3 representative inputs and an integer schedule seed")
    if (not isinstance(seeds, list) or len(seeds) < 2 or any(type(s) is not int for s in seeds)
            or len(set(seeds)) != len(seeds)):
        raise InputError("sensitivity needs at least two unique integer search seeds")
    if (not isinstance(budgets, list) or len(budgets) < 2
            or any(type(b) not in (int, float) or not math.isfinite(b) or b <= 0 for b in budgets)
            or len(set(budgets)) != len(budgets)):
        raise InputError("sensitivity time budgets must be at least two distinct positive finite values")
    if type(weight_seconds) not in (int, float) or not math.isfinite(weight_seconds) or weight_seconds <= 0:
        raise InputError("sensitivity weight_seconds must be positive and finite")
    if (not isinstance(profiles, list) or any(not isinstance(p, str) for p in profiles)
            or len(profiles) < 2 or "balanced" not in profiles
            or len(set(profiles)) != len(profiles)):
        raise InputError("sensitivity weight profiles must be unique and include balanced")
    weights = {p: list(profile_weights(p)) for p in profiles}
    extra = []
    for parent in groups:
        inputs = sorted(datasets_for(parent["config"]), key=lambda i: (len(i.orders), i.name.casefold()))
        indices = sorted({0, len(inputs) // 2, len(inputs) - 1})[:limit]
        selected = [inputs[i].to_dict() for i in indices]
        conditions = [(float(b), "balanced") for b in sorted(budgets)]
        conditions += [(float(weight_seconds), p) for p in profiles
                       if (float(weight_seconds), p) not in conditions]
        search = json.loads(json.dumps(asdict(SearchConfig(**parent["config"].get("search", {})).validate())))
        design = {"time_budgets": sorted(budgets), "weight_seconds": weight_seconds,
                  "profiles": weights, "search_seeds": seeds, "search": search,
                  "instance_sha256": {d["name"]: fingerprint(Instance.from_dict(d)) for d in selected},
                  "schedule_seed": order_seed,
                  "selection": "first/middle/last by order count and name; never by result",
                  "conditions": [{"name": f"{parent['name']}_sensitivity_{index:02d}",
                                  "seconds": seconds, "profile": profile}
                                 for index, (seconds, profile) in enumerate(conditions, 1)]}
        design_hash = _digest(design)
        parent["config"]["sensitivity_design"] = design
        for index, condition in enumerate(design["conditions"]):
            options = {**search, "seconds": condition["seconds"]}
            config = {"methods": deepcopy(parent["config"]["methods"]), "search_seeds": seeds,
                      "references": deepcopy(parent["config"].get("references", ["B0", "B2"])),
                      "weights": weights[condition["profile"]], "search": options,
                      "inline_instances": selected, "run_order_seed": order_seed + index,
                      "sensitivity_condition": {**condition, "parent": parent["name"],
                                                "design_sha256": design_hash}}
            runs = len(selected) * sum(len(seeds) if m in STOCHASTIC else 1 for m in config["methods"])
            extra.append({"name": condition["name"], "config": config,
                          "instances": len(selected), "runs": runs,
                          "instance_sha256": deepcopy(design["instance_sha256"])})
    if set(g["name"].casefold() for g in groups) & set(g["name"].casefold() for g in extra):
        raise InputError("Generated sensitivity names collide with an experiment group")
    random.Random(order_seed).shuffle(extra)
    return extra


def validate_conditions(payload):
    """Native results are already validated; audit the cross-condition pairing."""
    groups = {g["name"]: g for g in payload["groups"]}
    planned = set()
    for parent in payload["groups"]:
        design = parent["config"].get("sensitivity_design")
        if design is None:
            continue
        canonical_search = json.loads(json.dumps(asdict(
            SearchConfig(**parent["config"].get("search", {})).validate())))
        seeds = design["search_seeds"]
        if (design["search"] != canonical_search or len(seeds) < 2
                or any(type(s) is not int for s in seeds) or len(set(seeds)) != len(seeds)
                or "balanced" not in design["profiles"]
                or len(design["profiles"]) < 2
                or any(w != list(profile_weights(p)) for p, w in design["profiles"].items())):
            raise InputError("Invalid sensitivity search, seeds or named weight profiles")
        inputs = parent["instance_fingerprints"]
        hashes = design["instance_sha256"]
        if not 1 <= len(hashes) <= 3 or any(inputs.get(n) != h for n, h in hashes.items()):
            raise InputError("Sensitivity selected inputs differ from parent evidence")
        declared = design["conditions"]
        expected = {(float(b), "balanced") for b in design["time_budgets"]}
        expected |= {(float(design["weight_seconds"]), p) for p in design["profiles"]}
        if (len(declared) != len(expected)
                or {(c["seconds"], c["profile"]) for c in declared} != expected):
            raise InputError("Sensitivity condition inventory differs from the declared factors")
        for condition in declared:
            name = condition["name"]
            if name in planned or name not in groups:
                raise InputError("Missing or duplicate planned sensitivity condition")
            planned.add(name)
            group = groups[name]
            config = group["config"]
            marker = {**condition, "parent": parent["name"], "design_sha256": _digest(design)}
            options = {**design["search"], "seconds": condition["seconds"]}
            if (config.get("sensitivity_condition") != marker
                    or config.get("methods") != parent["config"]["methods"]
                    or config.get("search_seeds") != design["search_seeds"]
                    or config.get("search") != options
                    or config.get("weights") != design["profiles"][condition["profile"]]
                    or group["instance_fingerprints"] != hashes
                    or len(config["inline_instances"]) != len(hashes)
                    or {d["name"]: fingerprint(Instance.from_dict(d))
                        for d in config["inline_instances"]} != hashes):
                raise InputError("Sensitivity input, seed, search or weight pairing mismatch")
    actual = {g["name"] for g in payload["groups"] if "sensitivity_condition" in g["config"]}
    if actual != planned:
        raise InputError("Unplanned sensitivity conditions or missing parent design")


def condition_rows(payload, tables, parent=None):
    """Use the same audited means/SD as the viewer and exported source tables."""
    by_group = {g["name"]: g for g in payload["groups"]}
    rows = []
    for source in tables["per_instance"]:
        group = by_group[source["group"]]
        marker = group["config"].get("sensitivity_condition")
        if marker is None or (parent is not None and marker["parent"] != parent):
            continue
        runs = [r for r in group["results"]
                if r["instance"] == source["instance"] and r["method"] == source["method"]]
        rows.append({**source, "parent_group": marker["parent"], "profile": marker["profile"],
                     "budget_seconds": marker["seconds"],
                     "weights": list(group["config"]["weights"]),
                     "zero_iteration_runs": sum(r["search"]["iterations_completed"] == 0
                                                for r in runs if r["method"] in STOCHASTIC)})
    return rows

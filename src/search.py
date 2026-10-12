"""ALNS with full-objective insertion and explicit assignment/sequence neighborhoods."""
import math
import json
import random
import time
from dataclasses import asdict, dataclass

from .heuristics import freeze, mutable
from .models import InputError, number


class BudgetExpired(Exception):
    pass


@dataclass(frozen=True)
class SearchConfig:
    iterations: int = 200
    seconds: float = 3.0  # 0 means iteration-only, for deterministic regression tests
    removal_fraction: float = .15
    max_removed: int = 6
    candidate_limit: int = 24  # 0 enumerates all insertion positions
    temperature: float = .03
    cooling: float = .995
    reaction: float = .25
    segment: int = 20
    local_trials: int = 8
    local_every: int = 5
    cache_limit: int = 10000  # entries per cache; 0 is unbounded
    incremental_validation: bool = False
    destroy_operators: tuple[str, ...] = ("random", "related", "late", "batch")
    repair_operators: tuple[str, ...] = ("greedy", "regret2")
    candidate_policy: str = "uniform"  # guided is opt-in; preserve the legacy RNG path

    def validate(self):
        if self.candidate_policy not in ("uniform", "guided"):
            raise InputError("candidate_policy must be uniform or guided")
        if type(self.incremental_validation) is not bool:
            raise InputError("incremental_validation must be a boolean")
        for key, allowed in (("destroy_operators", {"random", "related", "late", "batch", "delay_chain"}),
                             ("repair_operators", {"greedy", "regret2"})):
            values = getattr(self, key)
            if (not isinstance(values, (tuple, list)) or not values
                    or any(not isinstance(v, str) or v not in allowed for v in values)
                    or len(values) != len(set(values))):
                raise InputError(f"{key} must be a nonempty list of unique supported operators")
        for key in ("iterations", "max_removed", "segment", "local_every"):
            value = getattr(self, key)
            if type(value) is not int or value < 1:
                raise InputError(f"{key} must be a positive integer")
        for key in ("candidate_limit", "local_trials", "cache_limit"):
            value = getattr(self, key)
            if type(value) is not int or value < 0:
                raise InputError(f"{key} must be a nonnegative integer")
        number(self.seconds, "seconds")
        number(self.temperature, "temperature", strict=True)
        for key in ("removal_fraction", "reaction", "cooling"):
            value = number(getattr(self, key), key, strict=True)
            if value > 1 or (key == "cooling" and value == 1):
                raise InputError(f"{key} must be at most 1 (cooling strictly less than 1)")
        return self


def canonical_search_config(config):
    """Validate supplied fields and fill defaults when reading older saved evidence."""
    return json.loads(json.dumps(asdict(SearchConfig(**config).validate())))


def deadline_check(deadline):
    if time.perf_counter() >= deadline:
        raise BudgetExpired


def destroy(ctx, plan, operator, rng, config, mode="2opt"):
    all_orders = [o for seq in plan for batch in seq for o in batch]
    count = min(len(all_orders), config.max_removed, max(1, math.ceil(len(all_orders) * config.removal_fraction)))
    if operator == "random":
        removed = rng.sample(all_orders, count)
    elif operator == "related":
        seed = rng.choice(all_orders)
        scale = max(ctx.objective.completion_ref, 1.)
        def related(oid):
            near = min(ctx.graph.distance(a, b) for a in ctx.locations[seed] for b in ctx.locations[oid])
            return (near / ctx.objective.distance_ref + abs(ctx.orders[seed].due - ctx.orders[oid].due) / scale, oid)
        removed = sorted(all_orders, key=related)[:count]
    elif operator == "late":
        records = ctx.evaluate(plan, mode, details=True)["orders"]
        removed = [row["id"] for row in sorted(records, key=lambda row: (-row["tardiness"], row["due"], row["id"]))[:count]]
    elif operator == "delay_chain":
        # Target the tightest batch and its immediate predecessor, whose duration
        # delays every order downstream. Repair still minimizes the full objective.
        batches = ctx.evaluate(plan, mode, details=True)["batches"]
        target = min(batches, key=lambda b: (min(ctx.orders[o].due for o in b["orders"]) - b["end"], b["id"]))
        chain = list(target["orders"])
        predecessors = [b for b in batches if b["picker"] == target["picker"] and b["position"] == target["position"] - 1]
        if predecessors:
            before = predecessors[0]["orders"]
            chain = [chain[0], *before, *chain[1:]]
        removed = chain[:count]
    elif operator == "batch":
        # Remove a whole batch even if larger than max_removed. It is a distinct neighborhood.
        removed = list(rng.choice([batch for sequence in plan for batch in sequence]))
    else:
        raise InputError(f"Unknown destroy operator {operator}")
    gone = set(removed)
    partial = tuple(tuple(tuple(o for o in batch if o not in gone) for batch in sequence if any(o not in gone for o in batch)) for sequence in plan)
    return partial, sorted(removed)


def guided_action_scores(ctx, plan, oid, actions, mode, deadline):
    """Cheap ranking proxy; every retained action is still scored by the full objective."""
    deadline_check(deadline)
    op, objective = ctx.instance.operations, ctx.objective
    singleton = ctx.batch_info((oid,), mode)
    data, picker_ends = [], []
    for sequence in plan:
        end, rows = 0., []
        for batch in sequence:
            deadline_check(deadline)
            info = ctx.batch_info(batch, mode)
            end += info[2]
            locations = frozenset().union(*(ctx.locations[o] for o in batch))
            rows.append((batch, end, locations))
        picker_ends.append(end)
        data.append(rows)
    late_suffix = []
    for rows in data:
        counts, late = [0] * (len(rows)+1), 0
        for index in range(len(rows)-1, -1, -1):
            batch, end, _ = rows[index]
            late += sum(end > ctx.orders[o].due for o in batch)
            counts[index] = late
        late_suffix.append(counts)
    old_makespan = max(picker_ends)
    scores = {}
    for action in actions:
        deadline_check(deadline)
        new, picker, index = action
        rows = data[picker]
        if new:
            distance, duration = singleton[1].distance, singleton[2]
            end = (rows[index-1][1] if index else 0.) + duration
            tardiness = max(0., end-ctx.orders[oid].due) + duration*late_suffix[picker][index]
        else:
            batch, old_end, locations = rows[index]
            missing = ctx.locations[oid]-locations
            anchors = locations | {ctx.instance.depot}
            distance = 2*sum(min(ctx.graph.distance(a,b) for b in anchors) for a in missing)
            duration = distance/op.speed + op.location_minutes*len(missing) + ctx.pick_times[oid]
            end = old_end + duration
            tardiness = max(0., end-ctx.orders[oid].due)
            tardiness += sum(max(0., end-ctx.orders[o].due)-max(0., old_end-ctx.orders[o].due) for o in batch)
            tardiness += duration*late_suffix[picker][index+1]
        makespan = max(old_makespan, picker_ends[picker]+duration)-old_makespan
        scores[action] = objective.score(distance, makespan, tardiness)
    return scores


def insertion_options(ctx, plan, oid, rng, limit, mode, deadline, policy="uniform"):
    actions, new_actions = [], []
    cap = ctx.instance.operations.capacity
    for picker, sequence in enumerate(plan):
        for index, batch in enumerate(sequence):
            if sum(ctx.loads[o] for o in batch) + ctx.loads[oid] <= cap + 1e-9:
                actions.append((False, picker, index))
        new_actions.extend((True, picker, index) for index in range(len(sequence) + 1))
    # At least one new-batch insertion is always represented; no silent dropped order.
    if limit and len(actions) + len(new_actions) > limit:
        mandatory = rng.choice(new_actions)
        others = [action for action in actions + new_actions if action != mandatory]
        if policy == "guided" and limit > 1:
            scores = guided_action_scores(ctx, plan, oid, others, mode, deadline)
            guided = sorted(others, key=lambda action: (scores[action], action))[:(limit-1)//2]
            remaining = [action for action in others if action not in guided]
            actions = [mandatory, *guided, *rng.sample(remaining, limit-1-len(guided))]
        else:
            actions = [mandatory, *rng.sample(others, min(limit - 1, len(others)))]
    else:
        actions += new_actions
    options = []
    for new, picker, index in sorted(actions):
        deadline_check(deadline)
        candidate = mutable(plan)
        if new:
            candidate[picker].insert(index, [oid])
        else:
            candidate[picker][index].append(oid)
        state = freeze(candidate)
        options.append((ctx.cost(state, mode, partial=True), state))
    options.sort(key=lambda item: (item[0], item[1]))
    return options


def repair(ctx, partial, removed, operator, rng, config, mode, deadline):
    pending = sorted(removed)
    while pending:
        deadline_check(deadline)
        choices = []
        for oid in pending:
            options = insertion_options(ctx, partial, oid, rng, config.candidate_limit, mode, deadline,
                                        policy=config.candidate_policy)
            if operator == "greedy":
                priority = (options[0][0], oid)
            elif operator == "regret2":
                regret = options[1][0] - options[0][0] if len(options) > 1 else float("inf")
                priority = (-regret, oid)
            else:
                raise InputError(f"Unknown repair operator {operator}")
            choices.append((priority, oid, options[0][1]))
        _, oid, partial = min(choices, key=lambda row: row[0])
        pending.remove(oid)
    ctx.check_plan(partial)
    return partial


def schedule_neighbor(plan, rng):
    candidate = mutable(plan)
    coordinates = [(p, b) for p, seq in enumerate(candidate) for b in range(len(seq))]
    if not coordinates:
        return plan
    source_picker, source_index = rng.choice(coordinates)
    if len(coordinates) > 1 and rng.random() < .5:
        target_picker, target_index = rng.choice([key for key in coordinates if key != (source_picker, source_index)])
        candidate[source_picker][source_index], candidate[target_picker][target_index] = candidate[target_picker][target_index], candidate[source_picker][source_index]
    else:
        batch = candidate[source_picker].pop(source_index)
        target_picker = rng.randrange(len(candidate))
        target_index = rng.randrange(len(candidate[target_picker]) + 1)
        candidate[target_picker].insert(target_index, batch)
    return freeze(candidate)


def order_neighbor(ctx, plan, rng):
    candidate = mutable(plan)
    batches = [batch for sequence in candidate for batch in sequence]
    if len(batches) < 2:
        return plan
    source, target = rng.sample(batches, 2)
    oid = rng.choice(source)
    if rng.random() < .5:
        other = rng.choice(target)
        source.remove(oid)
        target.remove(other)
        source.append(other)
    else:
        source.remove(oid)
    target.append(oid)
    if any(sum(ctx.loads[o] for o in b) > ctx.instance.operations.capacity + 1e-9 for b in (source, target)):
        return plan
    return freeze([[b for b in seq if b] for seq in candidate])


def local_search(ctx, plan, rng, trials, mode, deadline, schedule=True, orders=False):
    cost = ctx.cost(plan, mode)
    for _ in range(trials):
        deadline_check(deadline)
        choose_order = orders and rng.random() < .5
        if choose_order:
            candidate = order_neighbor(ctx, plan, rng)
        elif schedule:
            candidate = schedule_neighbor(plan, rng)
        else:
            continue
        candidate_cost = ctx.cost(candidate, mode)
        if candidate_cost < cost - 1e-12:
            plan, cost = candidate, candidate_cost
    return plan


def optimize(ctx, initial, seed=42, config=None, adaptive=True, schedule=True, mode="2opt", deadline=None):
    config = (config or SearchConfig()).validate()
    started = time.perf_counter()
    if deadline is None:
        deadline = started + config.seconds if config.seconds else float("inf")
    rng = random.Random(seed)
    current = best = initial
    current_cost = best_cost = ctx.cost(initial, mode)
    destroy_names = tuple(config.destroy_operators)
    repair_names = tuple(config.repair_operators)
    weights = {name: 1. for name in destroy_names + repair_names}
    uses = {name: 0 for name in weights}
    segment_uses = uses.copy()
    scores = {name: 0. for name in weights}
    temperature = config.temperature
    trace = [{"iteration": 0, "seconds": 0., "objective": best_cost}]
    accepted, iterations, stopped = 0, 0, "iterations"
    adaptation_updates, adapted_iterations = 0, 0

    def adapt():
        for name, weight in weights.items():
            if adaptive and segment_uses[name]:
                weights[name] = max(.05, (1 - config.reaction) * weight + config.reaction * scores[name] / segment_uses[name])
            segment_uses[name], scores[name] = 0, 0.

    for iteration in range(1, config.iterations + 1):
        try:
            deadline_check(deadline)
            destroy_op = rng.choices(destroy_names, weights=[weights[o] for o in destroy_names])[0]
            repair_op = rng.choices(repair_names, weights=[weights[o] for o in repair_names])[0]
            partial, removed = destroy(ctx, current, destroy_op, rng, config, mode)
            candidate = repair(ctx, partial, removed, repair_op, rng, config, mode, deadline)
            if iteration % config.local_every == 0:
                candidate = local_search(ctx, candidate, rng, config.local_trials, mode, deadline, schedule=schedule, orders=True)
            candidate_cost = ctx.cost(candidate, mode)
        except BudgetExpired:
            stopped = "time_limit"
            break
        iterations = iteration
        if adaptive and adaptation_updates:
            adapted_iterations += 1
        delta = candidate_cost - current_cost
        accept = delta <= 0 or rng.random() < math.exp(-delta / max(temperature, 1e-12))
        reward = 0.
        if accept:
            accepted += 1
            reward = 3. if delta < -1e-12 else 1.
            current, current_cost = candidate, candidate_cost
        if candidate_cost < best_cost - 1e-12:
            best, best_cost, reward = candidate, candidate_cost, 8.
            trace.append({"iteration": iteration, "seconds": time.perf_counter() - started, "objective": best_cost})
        for name in (destroy_op, repair_op):
            uses[name] += 1
            segment_uses[name] += 1
            scores[name] += reward
        if iteration % config.segment == 0:
            adapt()
            if adaptive:
                adaptation_updates += 1
        temperature *= config.cooling
    adapt()
    ctx.check_plan(best)
    trace.append({"iteration": iterations, "seconds": time.perf_counter() - started, "objective": best_cost})
    return best, {"seed": seed, "config": asdict(config), "adaptive": adaptive,
                  "schedule_neighborhoods": schedule, "iterations_completed": iterations,
                  "adaptation_updates": adaptation_updates,
                  "adapted_iterations": adapted_iterations, "accepted": accepted,
                  "stop_reason": stopped, "operator_weights": weights,
                  "operator_uses": uses, "trace": trace}

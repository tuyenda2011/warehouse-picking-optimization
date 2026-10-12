"""Shared labels, styling and input selection for evaluation charts."""
from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any

from ..benchmark import STOCHASTIC
from ..solver import METHODS


METHOD_STYLES = {
    "B0": ("#64748b", "s", "--"), "B1": ("#8c6d31", "v", ":"),
    "B2": ("#2563a8", "D", "--"), "B3": ("#9467bd", "^", "-."),
    "LNS": ("#d17a22", "P", "-."), "ALNS": ("#147d64", "o", "-"),
    "VNS": ("#c3485e", "X", ":"),
    "ALNS_NO_SCHEDULE": ("#80624b", "h", "--"),
    "ALNS_NO_2OPT": ("#208b9d", "*", "-."), "B-S": ("#797328", "<", ":"),
}


FAMILIES = {
    "quality": "Chất lượng nghiệm",
    "components": "Các thành phần mục tiêu",
    "stability": "Độ ổn định giữa các seed",
    "convergence": "Hội tụ theo thời gian thực",
    "scalability": "Thay đổi theo quy mô đơn hàng",
    "budget": "Độ nhạy ngân sách thời gian",
    "weights": "Đánh đổi theo trọng số",
}


def families_for(group):
    if "sensitivity_condition" in group["config"]:
        return []
    return list(FAMILIES) if "sensitivity_design" in group["config"] else list(FAMILIES)[:5]


METRIC_LABELS = {"distance": "Quãng đường", "makespan": "Thời gian hoàn tất", "tardiness": "Tổng trễ hạn"}


GROUP_LABELS = {"maps": "Các bản đồ", "scalability": "Quy mô", "kris": "Kris", "current_run": "Lần chạy hiện tại"}


MAP_LABELS = {"single_block": "Kho chuẩn", "double_block": "Kho 2 khối", "mega_hub": "Kho lớn",
              "rush_hour": "Cao điểm", "abc_zonal": "Phân khu ABC"}


def _slug(value: str) -> str:
    # Preserve valid trailing hyphens: maps and maps- are distinct cohort names.
    return re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip(".") or "group"


def _method_order(methods: Any) -> list[str]:
    return sorted(set(methods), key=lambda method: (METHODS.index(method) if method in METHODS else len(METHODS), method))


def _instance_order(instance: dict[str, Any]) -> tuple:
    # Selection depends only on input identity and order count, never on scores.
    return len(instance["orders"]), instance["name"].casefold()


def representative_instances(group: dict[str, Any]) -> list[str]:
    """Choose first/middle/last input identities deterministically, at most three."""
    instances = sorted(group["instances"], key=_instance_order)
    indices = sorted({0, len(instances) // 2, len(instances) - 1})
    return [instances[i]["name"] for i in indices] if instances else []


def _instance_labels(group: dict[str, Any]) -> dict[str, str]:
    """Shorten only identified source families; retain size, data seed and identity."""
    labels = {}
    for instance in group["instances"]:
        name, n = instance["name"], len(instance["orders"])
        metadata = instance.get("metadata", {})
        seed = metadata.get("seed")
        scenario = metadata.get("scenario", {})
        scenario_id = scenario.get("id") if isinstance(scenario, dict) else None
        source_name = name
        if isinstance(scenario_id, str) and scenario_id in MAP_LABELS:
            source_name = MAP_LABELS[scenario_id]
        elif metadata.get("source_kind") == "author_benchmark":
            match = re.fullmatch(r"Kris-instances_(\d+)_(\d+)", name)
            if match:
                source_name = f"Kris {match[1]}/{match[2]}"
        elif metadata.get("source") == "synthetic/internal-v1":
            match = re.fullmatch(r"(?:[\w]+-)?synthetic-n(\d+)-seed(-?\d+)", name)
            if match and int(match[1]) == n and int(match[2]) == seed:
                source_name = "Tổng hợp"
        labels[name] = f"{source_name} · {n} đơn" + (f" · seed {seed}" if seed is not None else "")
    counts = Counter(labels.values())
    for name, label in labels.items():
        if counts[label] > 1:
            labels[name] = f"{name} · {label}"
    return labels


def _label_caption(labels: dict[str, str], names: list[str]) -> str:
    return " Nhãn trên hình → ID đầy đủ: " + "; ".join(f"{labels[name]} → {name}" for name in names) + "."


def _runs_by_instance(group: dict[str, Any]) -> dict:
    runs = defaultdict(lambda: defaultdict(list))
    for result in group["results"]:
        runs[result["instance"]][result["method"]].append(result)
    return runs


def _spec(group: dict, family: str, caption: str = "", figure: Any = None, reason: str | None = None,
          suffix: str = "") -> dict[str, Any]:
    return {"id": f"{_slug(group['name'])}__{family}{suffix}",
            "title": f"{FAMILIES[family]} · {GROUP_LABELS.get(group['name'], group['name'])}", "group": group["name"], "caption": caption,
            "figure": figure, "reason": reason}


def _figure(width: float, height: float, style: str = "report"):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    # A slide is a complete canvas; report figures retain their natural sizes.
    size = (12.8, 7.2) if style == "presentation" else (width, height)
    figure = Figure(figsize=size, layout="constrained", facecolor="white")
    figure._evaluation_style = style
    FigureCanvasAgg(figure)
    return figure


def _clean_axis(axis, grid: str = "x") -> None:
    axis.set_facecolor("white")
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["bottom", "left"]].set_color("#cbd5e1")
    axis.tick_params(colors="#334155", length=3)
    axis.grid(axis=grid, color="#dfe5ec", linewidth=.65, zorder=0)
    axis.set_axisbelow(True)


def _legend(axis, methods: list[str], size: int) -> None:
    from matplotlib.lines import Line2D

    handles = [Line2D([], [], color=METHOD_STYLES[m][0], marker=METHOD_STYLES[m][1],
                      linestyle="none", markersize=6, label=m) for m in methods]
    axis.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, 1.02),
                ncols=min(5, len(methods)), frameon=False, fontsize=size)


def _eligible_seed_runs(method_runs: dict, trace: bool = False, single_run: bool = False) -> tuple[dict, list[str]]:
    eligible, excluded = {}, []
    for method in _method_order(m for m in method_runs if m in STOCHASTIC):
        runs = method_runs[method]
        if len({run["search"]["seed"] for run in runs}) < (1 if single_run else 2):
            excluded.append(f"{method}: cần ít nhất 2 search seed khác nhau")
        elif trace and any(len(run["search"].get("trace", [])) < 2 for run in runs):
            excluded.append(f"{method}: thiếu trace có ít nhất 2 quan sát")
        else:
            eligible[method] = sorted(runs, key=lambda run: run["search"]["seed"])
    return eligible, excluded

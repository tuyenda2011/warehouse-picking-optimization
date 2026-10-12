"""Presentation units anchored to the simulation; native evidence stays intact."""
from copy import deepcopy
import math

from src.demo_snapshot import validate_snapshot
from src.evaluation import evaluation_tables, validate_evaluation
from src.evaluation_figures import _figure_specs_from_tables, representative_instances
from src.models import InputError, Instance, Operations
from src.units import KRIS_DISPLAY_CONVENTION, display_snapshot


def kris_convention(instance):
    """Infer a demo time scale from the declared source speed, not measured data."""
    data = instance.to_dict() if isinstance(instance, Instance) else instance
    metadata = data.get("metadata", {})
    units = metadata.get("units", {})
    if (metadata.get("source_kind") != "author_benchmark"
            or not data.get("name", "").startswith("Kris-")
            or units.get("distance") != "source_distance_unit"
            or units.get("time") != "source_time_unit"):
        return None
    speed = data["operations"]["speed"]
    if (isinstance(speed, bool) or not isinstance(speed, (int, float))
            or not math.isfinite(speed) or speed <= 0):
        raise InputError("Kris source speed must be positive and finite")
    distance = KRIS_DISPLAY_CONVENTION["metres_per_source_distance"]
    anchor = Operations().speed
    return {
        "metres_per_source_distance": distance,
        "seconds_per_source_time": distance * speed * (60 / anchor),
        "simulation_anchor_speed_metres_per_minute": anchor,
    }


def display_snapshot_for_simulation(snapshot, converted=True):
    """Audit the native snapshot, then convert a copy using the simulation anchor."""
    validate_snapshot(snapshot)
    if not converted:
        return snapshot
    return display_snapshot(snapshot, kris_convention(snapshot["instance"]))


def kris_conversion_caption(instance):
    data = instance.to_dict() if isinstance(instance, Instance) else instance
    convention = data.get("metadata", {}).get("display_conversion")
    if not convention:
        return None
    source_distance = 1 / convention["metres_per_source_distance"]
    source_time = 1 / convention["seconds_per_source_time"]
    anchor = convention.get("simulation_anchor_speed_metres_per_minute", Operations().speed)
    return (f"Quy ước demo Kris: {source_distance:g} đơn vị khoảng cách = 1 m; "
            f"{source_time:g} đơn vị thời gian = 1 giây · tốc độ gốc mô phỏng {anchor:g} m/phút. "
            "Quy đổi minh họa; dữ liệu gốc được giữ nguyên.")


def has_kris_conversion(payload):
    return any(kris_convention(data) for group in payload["groups"] for data in group["instances"])


def _display_tables(payload, native_tables, converted):
    tables = deepcopy(native_tables)
    if not converted:
        return tables
    conventions = {(group["name"], data["name"]): kris_convention(data)
                   for group in payload["groups"] for data in group["instances"]}
    suffixes = ("", "_mean", "_median", "_std", "_best", "_difference")
    for collection in ("per_instance", "raw_metrics"):
        for row in tables[collection]:
            convention = conventions[(row["group"], row["instance"])]
            if not convention:
                continue
            factors = {"distance": convention["metres_per_source_distance"],
                       "makespan": convention["seconds_per_source_time"] / 60,
                       "tardiness": convention["seconds_per_source_time"] / 60}
            for metric, factor in factors.items():
                for suffix in suffixes:
                    key = metric + suffix
                    if row.get(key) is not None:
                        row[key] *= factor
            row.update(distance_unit="m", time_unit="phút", display_basis="simulation_convention",
                       metres_per_source_distance=convention["metres_per_source_distance"],
                       seconds_per_source_time=convention["seconds_per_source_time"])
    return tables


def display_evaluation_tables(payload, reference="B2", converted=True):
    """Validate original evidence before deriving unit-aware presentation rows."""
    validate_evaluation(payload)
    return _display_tables(payload, evaluation_tables(payload, reference), converted)


def display_figure_specs(payload, reference="B2", group=None, style="report", converted=True):
    """Render audited statistics without validating rescaled normalization floors."""
    validate_evaluation(payload)
    tables = _display_tables(payload, evaluation_tables(payload, reference), converted)
    specs = _figure_specs_from_tables(payload, tables, reference, group, style)
    import matplotlib

    font = 20 if style == "presentation" else 10
    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": font,
                                "axes.titlesize": font, "axes.labelsize": font,
                                "xtick.labelsize": font - 1, "ytick.labelsize": font - 1,
                                "figure.titlesize": font + 2}):
        for cohort in payload["groups"]:
            if "sensitivity_condition" in cohort["config"]:
                continue
            if group is None or cohort["name"] == group:
                specs.extend(_operational_figures(cohort, tables["per_instance"], style, converted))
    return specs


def display_convergence_specs(payload, group=None, style="report"):
    """Build only native F/CPU-time figures when the current-run tab needs them."""
    validate_evaluation(payload)
    if style not in ("report", "presentation"):
        raise InputError("Figure style must be report or presentation")
    groups = [cohort for cohort in payload["groups"] if group is None or cohort["name"] == group]
    if not groups:
        raise InputError(f"Unknown evaluation group: {group}")
    import matplotlib
    from src.evaluation_charts.common import _runs_by_instance
    from src.evaluation_charts.convergence import build_figures

    font = 20 if style == "presentation" else 10
    specs = []
    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": font,
                                "axes.titlesize": font, "axes.labelsize": font,
                                "xtick.labelsize": font - 1, "ytick.labelsize": font - 1,
                                "figure.titlesize": font + 2}):
        for cohort in groups:
            specs.extend(build_figures(cohort, _runs_by_instance(cohort), style))
    return specs


def _operational_figures(group, rows, style, converted):
    """Show measured operational means and seed SD for input-chosen examples."""
    from src.evaluation_charts.common import METHOD_STYLES, _figure, _instance_labels, _method_order

    specs = []
    names = representative_instances(group)
    labels = _instance_labels(group)
    for index, name in enumerate(names, 1):
        selected = [row for row in rows if row["group"] == group["name"] and row["instance"] == name]
        methods = _method_order(row["method"] for row in selected)
        by_method = {row["method"]: row for row in selected}
        figure = _figure(11.5, 4.2, style)
        axes = figure.subplots(1, 3)
        for axis, metric, label, unit in zip(
                axes, ("distance", "makespan", "tardiness"),
                ("Quãng đường", "Thời gian hoàn tất", "Tổng độ trễ"),
                (selected[0]["distance_unit"], selected[0]["time_unit"], selected[0]["time_unit"])):
            means = [by_method[method][metric + "_mean"] for method in methods]
            spread = [by_method[method][metric + "_std"] for method in methods]
            axis.bar(range(len(methods)), means, yerr=spread, capsize=3,
                     color=[METHOD_STYLES[method][0] for method in methods], alpha=.9)
            axis.set_xticks(range(len(methods)), methods, rotation=30 if len(methods) > 5 else 0)
            axis.set_ylabel(f"{label} ({unit})")
            axis.set_ylim(bottom=0)
            if all(value == 0 for value in means):
                axis.set_ylim(0, 1)
                axis.set_yticks([0])
                axis.text(.5, .5, "Không có độ trễ" if metric == "tardiness" else "Tất cả bằng 0",
                          transform=axis.transAxes, ha="center", va="center", color="#64748b")
            axis.grid(axis="y", color="#dfe5ec", linewidth=.65)
            axis.set_axisbelow(True)
            axis.spines[["top", "right"]].set_visible(False)
        title = f"Chỉ số vận hành · {labels[name]}"
        figure.suptitle(title, weight="bold")
        convention = ("Kris hiển thị theo quy ước mô phỏng; " if converted and
                      any(row.get("display_basis") for row in selected) else "Giữ đơn vị dữ liệu; ")
        specs.append({"id": f"{group['name']}__operations_example{index}", "group": group["name"],
                      "title": title, "figure": figure, "reason": None,
                      "caption": convention + "cột = trung bình seed, râu = độ lệch chuẩn giữa seed, "
                      "không phải khoảng tin cậy; một seed có độ lệch chuẩn 0. "
                      "Ví dụ chọn theo số đơn/tên dữ liệu trước khi xem điểm; "
                      "thời gian vận hành khác thời gian máy tính chạy thuật toán."})
    return specs

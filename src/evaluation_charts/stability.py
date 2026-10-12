"""Stability figures from audited benchmark runs."""
from __future__ import annotations

from .common import (
    GROUP_LABELS,
    METHOD_STYLES,
    _clean_axis,
    _eligible_seed_runs,
    _figure,
    _instance_labels,
    _label_caption,
    _spec,
    representative_instances,
)


def build_figures(group: dict, runs: dict, style: str) -> list[dict]:
    selected = representative_instances(group)
    labels = _instance_labels(group)
    panels, exclusions = [], []
    for name in selected:
        eligible, excluded = _eligible_seed_runs(runs[name])
        exclusions.extend(f"{name} / {entry}" for entry in excluded)
        if eligible:
            panels.append((name, eligible))
    if not panels:
        return [_spec(group, "stability", reason="Cần ít nhất 2 search seed khác nhau của một method ngẫu nhiên trên instance ví dụ đã chọn.")]
    caption = ("Chấm = từng search seed; hộp = Q1–Q3 và trung vị; râu = giới hạn 1,5 IQR; tất cả seed, kể cả ngoại lệ, đều được vẽ bằng chấm. "
               "Đây là độ phân tán seed, không phải khoảng tin cậy hoặc kiểm định. "
               f"Chọn cố định tối đa 3 ví dụ: đầu / giữa / cuối khi sắp theo số đơn rồi tên, trước khi xem điểm: {', '.join(selected)}. "
               "Seed được xếp tăng dần; không chọn seed tốt nhất. " + ("Không đủ dữ liệu: " + "; ".join(exclusions) if exclusions else ""))
    specs = []
    panel_sets = [[panel] for panel in panels]
    for subset in panel_sets:
        fig = _figure(11.8 if len(subset) > 1 else 8.5, 4.1, style)
        axes = fig.subplots(1, len(subset), squeeze=False)[0]
        for axis, (name, eligible) in zip(axes, subset):
            for index, (method, method_runs) in enumerate(eligible.items()):
                values = [run["metrics"]["objective"] for run in method_runs]
                color, marker, _ = METHOD_STYLES[method]
                axis.boxplot([values], positions=[index], widths=.48, patch_artist=True, manage_ticks=False,
                             showfliers=False, boxprops={"facecolor": color, "alpha": .15, "edgecolor": color},
                             medianprops={"color": color, "linewidth": 1.6},
                             whiskerprops={"color": color}, capprops={"color": color})
                offsets = [0] if len(values) == 1 else [(-.14 + .28 * i / (len(values) - 1)) for i in range(len(values))]
                axis.scatter([index + offset for offset in offsets], values, color=color, marker=marker,
                             s=56 if style == "presentation" else 32, edgecolors="white", linewidths=.4, zorder=3)
            methods = list(eligible)
            axis.set_xticks(range(len(methods)), [f"{m}\n{len(eligible[m])} seed" for m in methods], rotation=20 if len(methods) > 3 else 0)
            axis.set_title(labels[name], fontsize=18 if style == "presentation" else 12)
            axis.set_ylabel("F cuối cùng")
            _clean_axis(axis, "y")
        fig.suptitle(f"Độ ổn định giữa các seed · {GROUP_LABELS.get(group['name'], group['name'])}", weight="bold")
        suffix = f"_example{selected.index(subset[0][0]) + 1}"
        spec = _spec(group, "stability", caption + _label_caption(labels, [subset[0][0]]), fig, suffix=suffix)
        spec["title"] += f" · {labels[subset[0][0]]}"
        specs.append(spec)
    return specs

"""Paired per-instance objective improvement figures."""
from __future__ import annotations

from .common import (
    GROUP_LABELS, METHOD_STYLES, _clean_axis, _figure, _instance_labels,
    _instance_order, _label_caption, _legend, _method_order, _spec,
)


def build_figures(group: dict, rows: list[dict], reference: str, style: str) -> list[dict]:
    methods = _method_order(row["method"] for row in rows if row["method"] != reference)
    names = [i["name"] for i in sorted(group["instances"], key=_instance_order)]
    labels = _instance_labels(group)
    by_key = {(row["instance"], row["method"]): row for row in rows}
    if not methods or not any(row.get("objective_improvement_pct") is not None for row in rows if row["method"] != reference):
        return [_spec(group, "quality", reason=f"Không có cặp instance hợp lệ với tham chiếu {reference}; F tham chiếu bằng 0 là N/A.")]
    specs = []
    page_size = 6 if style == "presentation" else 9
    for page, start in enumerate(range(0, len(names), page_size), 1):
        selected = names[start:start + page_size]
        fig = _figure(10, max(3.7, 2 + len(selected) * .55), style)
        axis = fig.subplots()
        offsets = [(index - (len(methods) - 1) / 2) * min(.085, .66 / max(1, len(methods))) for index in range(len(methods))]
        missing = 0
        for method, offset in zip(methods, offsets):
            points = [(index + offset, by_key.get((name, method), {}).get("objective_improvement_pct")) for index, name in enumerate(selected)]
            valid = [(y, value) for y, value in points if value is not None]
            missing += len(points) - len(valid)
            color, marker, _ = METHOD_STYLES[method]
            axis.scatter([value for _, value in valid], [y for y, _ in valid],
                         color=color, marker=marker, s=46, edgecolors="white", linewidths=.45, zorder=3)
        axis.axvline(0, color="#64748b", linewidth=1)
        axis.set_yticks(range(len(selected)), [labels[name] for name in selected])
        axis.set_ylim(len(selected) - .5, -.5)
        axis.set_xlabel(f"Cải thiện F so với {reference} (%)")
        axis.set_ylabel("Bản đồ" if group["name"] == "maps" else "Bộ dữ liệu")
        _clean_axis(axis)
        _legend(axis, methods, 15 if style == "presentation" else 9)
        page_title = f" · trang {page}" if len(names) > page_size else ""
        fig.suptitle(f"Chất lượng nghiệm · {GROUP_LABELS.get(group['name'], group['name'])}" + page_title, weight="bold")
        caption = (f"Mỗi điểm = 100 × (F trung bình seed của {reference} − F trung bình seed của method) / "
                   f"F trung bình seed của {reference} trên cùng instance; khớp per_instance.csv. "
                   "Mỗi instance có một trọng số; không gộp đơn vị hoặc nhóm dữ liệu. "
                   f"{len(selected)} / {len(names)} instance ở trang này; {missing} điểm thiếu hoặc mẫu số 0 là N/A (không vẽ). "
                   "Không hiển thị khoảng tin cậy.") + _label_caption(labels, selected)
        spec = _spec(group, "quality", caption, fig, suffix=f"_p{page}" if len(names) > page_size else "")
        spec["title"] += page_title
        specs.append(spec)
    return specs

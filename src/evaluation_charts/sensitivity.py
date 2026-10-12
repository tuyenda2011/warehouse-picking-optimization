"""Paired requested-budget curves and operational weight trade-offs."""
from matplotlib.lines import Line2D

from .common import GROUP_LABELS, METHOD_STYLES, _clean_axis, _figure, _instance_labels, _spec
from ..sensitivity import condition_rows

PROFILE_LABELS = {"balanced": "Cân bằng", "distance": "Ưu tiên đường đi",
                  "makespan": "Ưu tiên hoàn tất", "tardiness": "Ưu tiên độ trễ"}
PROFILE_MARKERS = {"balanced": "o", "distance": "^", "makespan": "D", "tardiness": "s"}


def build_figures(payload, parent, tables, style):
    design = parent["config"].get("sensitivity_design")
    if design is None:
        return []
    rows = condition_rows(payload, tables, parent["name"])
    labels = _instance_labels(parent)
    specs = []
    for index, name in enumerate(design["instance_sha256"], 1):
        subset = [row for row in rows if row["instance"] == name]
        by = {(row["profile"], row["budget_seconds"], row["method"]): row for row in subset}
        figure = _figure(9, 5.2, style)
        axis = figure.subplots()
        for method in parent["config"]["methods"]:
            selected = [by["balanced", budget, method] for budget in design["time_budgets"]]
            color, marker, line = METHOD_STYLES[method]
            axis.errorbar(design["time_budgets"], [r["objective_mean"] for r in selected],
                          yerr=[r["objective_std"] for r in selected], label=method,
                          color=color, marker=marker, linestyle=line, capsize=3, linewidth=1.5)
        axis.set(xlabel="Ngân sách khởi tạo + tìm kiếm yêu cầu (giây)",
                 ylabel="F cuối cùng", xticks=design["time_budgets"])
        _clean_axis(axis, grid="y")
        axis.legend(ncols=min(5, len(parent["config"]["methods"])), fontsize="small")
        figure.suptitle(f"Độ nhạy ngân sách · {labels[name]}", weight="bold")
        budget_rows = [r for r in subset if r["profile"] == "balanced"
                       and r["budget_seconds"] in design["time_budgets"]]
        zero = sum(r["zero_iteration_runs"] for r in budget_rows)
        caption = (f"Cùng input và {len(design['search_seeds'])} seed giữa các ngân sách; trọng số cân bằng. "
                   "Điểm = trung bình seed; râu = SD giữa seed, không phải khoảng tin cậy. "
                   "Trục x là ngân sách yêu cầu, không phải thời gian chạy thực đo. "
                   "Các điều kiện được chạy riêng theo thứ tự xáo cố định; không ép F giảm đơn điệu. "
                   f"Giữ cả {zero} lượt tìm kiếm hoàn thành 0 vòng. B0/B2 là heuristic tất định. "
                   "Các đường nối chỉ hướng dẫn đọc các ngân sách đã đo; không ngoại suy. "
                   f"Nhóm {GROUP_LABELS.get(parent['name'], parent['name'])}; đầu vào chọn trước kết quả.")
        spec = _spec(parent, "budget", caption, figure, suffix=f"_example{index}")
        spec["title"] += f" · {labels[name]}"
        specs.append(spec)

        figure = _figure(9, 5.2, style)
        axis = figure.subplots()
        for profile in design["profiles"]:
            for method in parent["config"]["methods"]:
                row = by[profile, design["weight_seconds"], method]
                axis.errorbar(row["distance_mean"], row["tardiness_mean"],
                              xerr=row["distance_std"], yerr=row["tardiness_std"],
                              color=METHOD_STYLES[method][0], marker=PROFILE_MARKERS[profile],
                              linestyle="none", capsize=3, markersize=7, alpha=.85)
        row = subset[0]
        axis.set(xlabel=f"Quãng đường ({row['distance_unit']})",
                 ylabel=f"Tổng độ trễ ({row['time_unit']})")
        handles = [Line2D([], [], color=METHOD_STYLES[m][0], marker="o", linestyle="none", label=m)
                   for m in parent["config"]["methods"]]
        legend = axis.legend(handles=handles, title="Thuật toán", loc="upper left",
                             bbox_to_anchor=(1.01, 1), fontsize="small")
        axis.add_artist(legend)
        axis.legend(handles=[Line2D([], [], color="#334155", marker=PROFILE_MARKERS[p],
                                    linestyle="none", label=PROFILE_LABELS[p])
                             for p in design["profiles"]],
                    title="Trọng số", loc="lower left", bbox_to_anchor=(1.01, 0), fontsize="small")
        _clean_axis(axis, grid="both")
        figure.suptitle(f"Đánh đổi theo trọng số · {labels[name]}", weight="bold")
        caption = (f"Cùng input, {len(design['search_seeds'])} seed và ngân sách {design['weight_seconds']:g} giây. "
                   "Điểm = trung bình seed; râu ngang/dọc = SD của quãng đường/độ trễ, không phải khoảng tin cậy. "
                   "Màu chỉ thuật toán, hình ký hiệu chỉ profile; các điểm bằng nhau có thể chồng nhau. "
                   "So sánh chỉ tiêu vận hành, không so F giữa các trọng số; không khẳng định biên Pareto tối ưu. "
                   "Giữ đơn vị của từng đầu vào và mọi điều kiện, không chọn điểm thuận lợi. "
                   f"Trọng số (D,C,T): {design['profiles']}.")
        spec = _spec(parent, "weights", caption, figure, suffix=f"_example{index}")
        spec["title"] += f" · {labels[name]}"
        specs.append(spec)
    return specs

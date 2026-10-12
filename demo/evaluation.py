"""Read-only assessment views backed by the portable evaluation API."""
from itertools import islice
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from src.evaluation import evaluation_tables, load_evaluation, snapshot_evaluation
from src.evaluation_figures import GROUP_LABELS, MAP_LABELS, figure_bytes
from demo.display import display_convergence_specs, display_evaluation_tables, display_figure_specs, has_kris_conversion
from demo.evaluation_text import localize_spec


VIEW_ERRORS = (ValueError, OSError, KeyError, TypeError)
SIMULATION = "Mô phỏng"
BENCHMARK = "Đánh giá benchmark"


def remember_evaluation_upload(state):
    """Keep uploaded bytes outside widget state; explicit removal clears them."""
    upload = state.get("evaluation_upload")
    if upload is None:
        if state.get("workspace", BENCHMARK) != BENCHMARK:
            state["benchmark_upload_widget_populated"] = False
            return
        if state.get("benchmark_upload_widget_populated", False):
            close_evaluation_upload(state)
        return
    state["_benchmark_upload_bytes"] = upload.getvalue()
    state["_benchmark_upload_name"] = upload.name
    state["_benchmark_input_mode"] = "upload"
    state["benchmark_upload_widget_populated"] = True


def close_evaluation_upload(state):
    state.pop("_benchmark_upload_bytes", None)
    state.pop("_benchmark_upload_name", None)
    state["_benchmark_input_mode"] = "local"
    state["benchmark_upload_widget_populated"] = False


def reset_hidden_evaluation_upload(state):
    """Drop a stale widget object before recreating the uploader, keeping bytes."""
    if not state.get("benchmark_upload_widget_hidden", False):
        return
    state.pop("evaluation_upload", None)
    state["benchmark_upload_widget_populated"] = False
    state["benchmark_upload_widget_hidden"] = False


def _upload_changed():
    remember_evaluation_upload(st.session_state)


def _local_report_changed():
    close_evaluation_upload(st.session_state)


def _close_retained_upload():
    close_evaluation_upload(st.session_state)


def discover_evaluations(root, limit=40):
    """Inspect a bounded number of immediate results directories, never JSON paths."""
    workspace = Path(root).resolve()
    results = (workspace / "results").resolve()
    if not results.is_relative_to(workspace) or not results.is_dir():
        return []
    found = []
    for directory in islice(results.iterdir(), limit):
        try:
            candidate = (directory / "report" / "evaluation.json").resolve()
            if candidate.is_relative_to(results) and candidate.is_file():
                found.append(candidate)
        except OSError:
            continue
    return sorted(found)


@st.cache_data(show_spinner=False, max_entries=16)
def validated_content(content):
    """Cache the audit by actual bytes, including for local report files."""
    return load_evaluation(content)


@st.cache_data(show_spinner=False, max_entries=8)
def current_evaluation(snapshot):
    return snapshot_evaluation(snapshot)


@st.cache_data(show_spinner=False, max_entries=16)
def presentation_tables(payload, reference, converted=True):
    return display_evaluation_tables(payload, reference=reference, converted=converted)


def references_for(group):
    methods = {result["method"] for result in group["results"]}
    preferred = ["B2", "B0", "B3", "LNS", "ALNS", "VNS"]
    return [method for method in preferred if method in methods] + sorted(methods - set(preferred))


@st.cache_data(show_spinner=False, max_entries=16)
def chart_inventory(payload, reference, group, style="report", converted=True):
    """List figure choices without encoding hidden figures as large PNGs."""
    specs = display_figure_specs(payload, reference=reference, group=group, style=style, converted=converted)
    choices = []
    try:
        for spec in specs:
            localized = localize_spec(spec, reference)
            choices.append({key: localized.get(key) for key in ("id", "title", "caption", "reason", "technical_caption")})
    finally:
        for spec in specs:
            if spec.get("figure") is not None:
                plt.close(spec["figure"])
    return choices


@st.cache_data(show_spinner=False, max_entries=24)
def chart_assets(payload, reference, group, style="report", converted=True, selected_id=None, family=None):
    """Share report figures and encode them once for display and downloads."""
    assets = []
    specs = (display_convergence_specs(payload, group=group, style=style) if family == "convergence" else
             display_figure_specs(payload, reference=reference, group=group, style=style, converted=converted))
    try:
        for spec in specs:
            if selected_id is not None and spec["id"] != selected_id:
                continue
            if family is not None and f"__{family}" not in spec["id"]:
                continue
            spec = localize_spec(spec, reference)
            asset = {key: spec.get(key) for key in ("id", "title", "caption", "reason", "technical_caption")}
            fig = spec.get("figure")
            asset["png"] = figure_bytes(fig, format="png") if fig is not None else None
            assets.append(asset)
    finally:
        for spec in specs:
            if spec.get("figure") is not None:
                plt.close(spec["figure"])
    return assets


def summary_frame(rows):
    labels = {"method": "Thuật toán", "reference": "Đối chứng", "instances": "Số bài toán",
              "win": "Thắng", "tie": "Hòa", "loss": "Thua", "mean_improvement_pct": "Cải thiện F (%)"}
    return pd.DataFrame([{labels[key]: row[key] for key in labels} for row in rows])


def instance_frame(rows, current=False, instances=()):
    if current:
        if not rows:
            return pd.DataFrame()
        labels = {"method": "Thuật toán", "objective_mean": "F",
                  "distance_mean": f"Quãng đường ({rows[0]['distance_unit']})",
                  "makespan_mean": f"Thời gian hoàn tất ({rows[0]['time_unit']})",
                  "tardiness_mean": f"Tổng độ trễ ({rows[0]['time_unit']})",
                  "late_orders_mean": "Đơn trễ", "total_seconds_mean": "Thời gian chạy (s)",
                  "objective_improvement_pct": "Cải thiện F (%)"}
        return pd.DataFrame([{labels[key]: row[key] for key in labels} for row in rows])
    map_names = {}
    for instance in instances:
        scenario = instance.get("metadata", {}).get("scenario", {})
        scenario_id = scenario.get("id") if isinstance(scenario, dict) else None
        if isinstance(scenario_id, str) and scenario_id in MAP_LABELS:
            map_names[instance["name"]] = MAP_LABELS[scenario_id]
    name_column = "Bản đồ" if map_names else "Bài toán"
    show_seed = any(row["instance_seed"] is not None for row in rows)
    return pd.DataFrame([{
        name_column: map_names.get(row["instance"], row["instance"]), "Số đơn": row["n"],
        **({"Seed dữ liệu": row["instance_seed"]} if show_seed else {}),
        "Thuật toán": row["method"], "Số lần chạy": row["runs"],
        "F trung bình ± độ lệch chuẩn": f"{row['objective_mean']:.4f} ± {row['objective_std']:.4f}",
        "Quãng đường": f"{row['distance_mean']:.3f} {row['distance_unit']}",
        "Thời gian hoàn tất": f"{row['makespan_mean']:.3f} {row['time_unit']}",
        "Tổng độ trễ": f"{row['tardiness_mean']:.3f} {row['time_unit']}",
        "Đơn trễ trung bình": row["late_orders_mean"],
        "Thời gian chạy (s)": row["total_seconds_mean"],
        "Cải thiện F (%)": row["objective_improvement_pct"],
    } for row in rows])


def table_view(rows, name, key, display=None, native_rows=None):
    frame = pd.DataFrame(rows)
    if frame.empty:
        st.info("Chưa có kết quả để so sánh với đối chứng đã chọn trong nhóm này.")
        return
    st.dataframe(frame if display is None else display, hide_index=True, width="stretch", height=320)
    converted = native_rows is not None and any(row.get("display_basis") for row in rows)
    suffix = "_simulation_units" if converted else ""
    label = f"Tải bảng {name} theo mô phỏng (CSV)" if converted else f"Tải bảng {name} (CSV)"
    st.download_button(label, frame.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{key}{suffix}.csv", mime="text/csv", key=f"download_{key}")
    if converted:
        st.download_button(f"Tải bảng {name} đơn vị gốc (CSV)",
                           pd.DataFrame(native_rows).to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"{key}_native_units.csv", mime="text/csv", key=f"download_{key}_native")


def chart_view(asset, key):
    if asset["png"] is None:
        st.info(asset["reason"] or "Chưa đủ dữ liệu để vẽ biểu đồ này.")
    else:
        st.image(asset["png"], width="stretch")
        st.download_button(
            "Tải hình PNG", asset["png"], file_name=f"{asset['id']}.png",
            mime="image/png", key=f"{key}_{asset['id']}_png",
        )
    if asset.get("caption") or asset.get("technical_caption"):
        with st.expander("Cách tính và phạm vi dữ liệu", expanded=False):
            if asset.get("caption"):
                st.caption(asset["caption"])
            if asset.get("technical_caption"):
                st.caption(asset["technical_caption"])


def figure_label(asset):
    for suffix, label in (("_distance", "Quãng đường"), ("_makespan", "Thời gian hoàn tất"), ("_tardiness", "Tổng độ trễ")):
        if asset["id"].endswith(suffix):
            return asset["title"] if asset["title"].endswith(f" · {label}") else f"{asset['title']} · {label}"
    page = asset["id"].rsplit("_p", 1)
    if len(page) == 2 and page[1].isdigit():
        suffix = f" · Trang {page[1]}"
        return asset["title"] if asset["title"].casefold().endswith(suffix.casefold()) else f"{asset['title']}{suffix}"
    return asset["title"]


def error_details(error):
    with st.expander("Chi tiết lỗi", expanded=False):
        st.text(str(error))


def benchmark_workspace(root):
    st.title("Đánh giá benchmark")
    with st.sidebar:
        st.header("Mở kết quả đánh giá")
        reset_hidden_evaluation_upload(st.session_state)
        upload = st.file_uploader(
            "Tải tệp evaluation.json", type=["json"], key="evaluation_upload",
            help="Tệp kết quả đầy đủ của đợt thực nghiệm, gồm dữ liệu đầu vào và các phương án đã tính.",
            on_change=_upload_changed,
        )
        if upload is not None and "_benchmark_input_mode" not in st.session_state:
            remember_evaluation_upload(st.session_state)
        st.session_state["benchmark_upload_widget_populated"] = upload is not None
        if upload is None and "_benchmark_upload_bytes" in st.session_state:
            st.caption(f"Tệp đang mở: {st.session_state['_benchmark_upload_name']}")
            st.button("Đóng tệp", key="close_evaluation_upload", on_click=_close_retained_upload)
        try:
            local_paths = discover_evaluations(root)
        except VIEW_ERRORS as exc:
            local_paths = []
            st.caption("Không đọc được danh sách báo cáo trên máy. Bạn vẫn có thể tải tệp evaluation.json lên.")
            error_details(exc)
        choices = {path.relative_to(Path(root).resolve()).as_posix(): path for path in local_paths}
        placeholder = "Chọn báo cáo trên máy"
        options = [placeholder, *choices]
        if st.session_state.get("evaluation_local") not in options:
            st.session_state["evaluation_local"] = placeholder
        local_choice = st.selectbox("Báo cáo trên máy", options, key="evaluation_local",
                                    help="Chọn báo cáo trên máy để thay tệp đang mở.",
                                    on_change=_local_report_changed)

    try:
        if (st.session_state.get("_benchmark_input_mode") == "upload"
                and "_benchmark_upload_bytes" in st.session_state):
            content = st.session_state["_benchmark_upload_bytes"]
            label = st.session_state["_benchmark_upload_name"]
        elif local_choice in choices:
            path = choices[local_choice]
            content, label = path.read_bytes(), local_choice
        else:
            st.info("Tải tệp evaluation.json hoặc chọn báo cáo đã lưu để bắt đầu. Không cần chạy mô phỏng trước.")
            return
        payload = validated_content(content)
        mode = {"quick": "Quick — chạy thử", "report": "Report — thực nghiệm đầy đủ",
                "live": "Lần chạy hiện tại"}.get(payload["preset"], payload["preset"])
        st.caption(f"{label} · {mode}")
        if payload["preset"] == "quick":
            st.warning("Chế độ Quick: chạy thử, chưa đủ để kết luận về các thuật toán.")
        groups = {group["name"]: group for group in payload["groups"]
                  if "sensitivity_condition" not in group["config"]}
        if st.session_state.get("evaluation_group") not in groups:
            st.session_state["evaluation_group"] = next(iter(groups))
        group_column, reference_column = st.columns(2)
        chosen = group_column.selectbox("Nhóm dữ liệu", list(groups), key="evaluation_group",
                                        format_func=lambda name: GROUP_LABELS.get(name, name))
        references = references_for(groups[chosen])
        if st.session_state.get("evaluation_reference") not in references:
            st.session_state["evaluation_reference"] = references[0]
        reference = reference_column.selectbox("Thuật toán đối chứng", references, key="evaluation_reference")
        config = groups[chosen]["config"]
        search = groups[chosen]["results"][0]["search"]["config"]
        weights = config.get("weights", [1/3, 1/3, 1/3])
        time_limit = f"{search['seconds']:g} giây" if search["seconds"] else "không giới hạn thời gian"
        selected_payload = {**payload, "groups": [group for group in payload["groups"]
                            if group["name"] == chosen or
                            group["config"].get("sensitivity_condition", {}).get("parent") == chosen]}
        if has_kris_conversion(selected_payload):
            st.caption("Quy ước Kris: 10 đơn vị khoảng cách = 1 m; thời gian suy ra theo tốc độ mô phỏng "
                       "60 m/phút. Quy đổi minh họa, chưa hiệu chuẩn; F và thời gian chạy máy tính giữ nguyên.")
        native_tables = evaluation_tables(selected_payload, reference=reference)
        tables = presentation_tables(selected_payload, reference=reference, converted=True)
        all_tables, all_native_tables = tables, native_tables
        tables = {key: [row for row in rows if row["group"] == chosen] for key, rows in tables.items()}
        native_tables = {key: [row for row in rows if row["group"] == chosen]
                         for key, rows in native_tables.items()}
        summary, instances, charts = st.tabs(["Tổng hợp", "Từng bài toán", "Biểu đồ"],
                                            key="benchmark_tabs", on_change="rerun")
        with summary:
            if summary.open:
                table_view(tables["summary"], "tổng hợp", "benchmark_summary", summary_frame(tables["summary"]))
        with instances:
            if instances.open:
                table_view(tables["per_instance"], "từng bài toán", "benchmark_per_instance",
                           instance_frame(tables["per_instance"], instances=groups[chosen]["instances"]),
                           native_rows=native_tables["per_instance"])
                with st.expander("Bảng đầy đủ và kết quả từng lần chạy", expanded=False):
                    st.dataframe(pd.DataFrame(tables["per_instance"]), hide_index=True, width="stretch", height=320)
                    table_view(tables["raw_metrics"], "từng lần chạy", "benchmark_raw_metrics",
                               native_rows=native_tables["raw_metrics"])
        with charts:
            if charts.open:
                style_column, figure_column = st.columns([1, 3])
                use = style_column.selectbox("Dùng cho", ["Báo cáo", "Slide"], key="evaluation_style")
                style = "report" if use == "Báo cáo" else "presentation"
                assets = chart_inventory(selected_payload, reference, chosen, style, converted=True)
                by_id = {asset["id"]: asset for asset in assets}
                if by_id:
                    if st.session_state.get("evaluation_figure") not in by_id:
                        st.session_state["evaluation_figure"] = next(iter(by_id))
                    figure_id = figure_column.selectbox(
                        "Chọn biểu đồ", list(by_id), format_func=lambda value: figure_label(by_id[value]),
                        key="evaluation_figure",
                    )
                    selected_asset = chart_assets(selected_payload, reference, chosen, style,
                                                  converted=True, selected_id=figure_id)[0]
                    chart_view(selected_asset, "benchmark")
                    if "__budget" in figure_id or "__weights" in figure_id:
                        from src.sensitivity import condition_rows
                        with st.expander("Dữ liệu độ nhạy và cấu hình", expanded=False):
                            st.caption("Cùng đầu vào và seed giữa các điều kiện. Râu là SD giữa seed. "
                                       "Chỉ so F trong cùng bộ trọng số; khảo sát bổ sung mang tính thăm dò.")
                            table_view(condition_rows(selected_payload, all_tables, chosen), "độ nhạy",
                                       "benchmark_sensitivity",
                                       native_rows=condition_rows(selected_payload, all_native_tables, chosen))
                else:
                    st.info("Chưa có biểu đồ cho nhóm dữ liệu này.")
        with st.expander("Thiết lập và cách tính", expanded=False):
            st.caption(f"{len(config.get('search_seeds', [7]))} seed khác nhau · "
                       f"Giới hạn tìm kiếm: {time_limit}, tối đa {search['iterations']} vòng.")
            st.caption(f"Trọng số cho quãng đường / thời gian hoàn tất / tổng độ trễ: "
                       f"{weights[0]:.3f} / {weights[1]:.3f} / {weights[2]:.3f}.")
            st.caption("Với mỗi bài toán, lấy trung bình các lần chạy trước khi so sánh. Mỗi bài toán có trọng số như nhau. Seed xác định yếu tố ngẫu nhiên của lần chạy; độ lệch chuẩn cho biết mức dao động giữa các lần chạy, không phải khoảng tin cậy. Kris hiển thị cùng quy ước đơn vị với mô phỏng; CSV đơn vị gốc được tải riêng.")
    except VIEW_ERRORS as exc:
        if isinstance(exc, OSError):
            st.error("Không đọc được tệp đã chọn. Hãy kiểm tra tệp còn trên máy và ứng dụng có quyền đọc tệp.")
        else:
            st.error("Tệp đánh giá không hợp lệ. Hãy dùng evaluation.json được xuất từ đợt thực nghiệm hoặc báo cáo.")
        error_details(exc)


def current_run_view(snapshot, selected):
    """Audit native evidence and show the same operational units as simulation."""
    st.warning("Một bài toán, một seed: chỉ phản ánh lần chạy này.")
    try:
        payload = current_evaluation(snapshot)
        uses_conversion = has_kris_conversion(payload)
        st.caption(f"Phương án đang xem: {selected} · " +
                   ("Chỉ số dùng cùng quy ước minh họa với mô phỏng; F và thời gian chạy giữ nguyên."
                    if uses_conversion else "Chỉ số giữ đơn vị gốc của dữ liệu."))
        group = payload["groups"][0]
        references = [method for method in ("B2", "B0") if method in references_for(group)]
        if st.session_state.get("objective_reference") not in references:
            st.session_state["objective_reference"] = references[0]
        reference = st.selectbox("Thuật toán đối chứng", references, key="objective_reference")
        native_tables = evaluation_tables(payload, reference=reference)
        tables = presentation_tables(payload, reference=reference, converted=True)
        result = snapshot["results"][selected]
        weights = result["objective_config"]["weights"]
        st.write(f"**Điểm F của {selected}: {result['metrics']['objective']:.4f}** · Đối chứng: {reference}")
        selected_row = next(row for row in tables["per_instance"] if row["method"] == selected)
        changes = []
        for metric, label in (("objective", "F"), ("distance", "quãng đường")):
            change = selected_row[f"{metric}_improvement_pct"]
            if change is None:
                changes.append(f"không tính tỷ lệ thay đổi của {label} vì giá trị đối chứng bằng 0")
            elif abs(change) < 1e-9:
                changes.append(f"{label} không đổi")
            else:
                changes.append(f"{label} {'giảm' if change > 0 else 'tăng'} {abs(change):.2f}%")
        late = selected_row["late_orders_difference"]
        changes.append("số đơn trễ không đổi" if abs(late) < 1e-9 else
                       f"số đơn trễ {'tăng' if late > 0 else 'giảm'} {abs(late):g} đơn")
        st.write(f"So với {reference}: {'; '.join(changes)}.")
        table_view(tables["per_instance"], "đánh giá lần chạy", "current_run_per_instance",
                   instance_frame(tables["per_instance"], current=True),
                   native_rows=native_tables["per_instance"])
        with st.expander("Chỉ số đầy đủ của lần chạy", expanded=False):
            st.caption(f"Trọng số cho quãng đường / thời gian hoàn tất / tổng độ trễ: {weights[0]:.3f} / {weights[1]:.3f} / {weights[2]:.3f}. F thấp hơn chưa chắc mọi chỉ số đều tốt hơn.")
            st.dataframe(pd.DataFrame(tables["per_instance"]), hide_index=True, width="stretch", height=320)
        convergence = chart_assets(payload, reference, group["name"], converted=True, family="convergence")
        for asset in convergence:
            chart_view(asset, "current_run")
    except VIEW_ERRORS as exc:
        st.error("Không thể đọc kết quả của lần chạy này để đánh giá. Hãy mở lại kết quả đã lưu hoặc chạy lại.")
        error_details(exc)

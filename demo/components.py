"""Views and controls for the warehouse demo."""
import json
import math

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from demo.simulation import render_simulation
from demo.evaluation import SIMULATION, current_run_view
from demo.display import display_snapshot_for_simulation, kris_conversion_caption
from demo.state import KRIS, SYNTHETIC, UPLOAD, improvement, upload_digest
from src.generator import MAP_SCENARIOS
from src.evaluation_figures import MAP_LABELS
from src.models import Instance
from src.objectives import WEIGHT_PROFILES
from src.plots import gantt_figure, warehouse_figure
from src.units import format_duration, time_scale_seconds, unit_label


def style():
    st.markdown("""<style>
    .stMainBlockContainer {max-width:1440px;padding:3.5rem 1.5rem 1.25rem;}
    .stMainBlockContainer [data-testid="stVerticalBlock"] {gap:.5rem;}
    h1 {font-size:1.75rem !important;letter-spacing:-.025em;padding:.15rem 0 .4rem !important;line-height:1.2;}
    h2 {font-size:1.375rem !important;}
    h3 {font-size:1.1rem !important;}
    [data-testid="stMetric"] {padding:2px 0;}
    [data-testid="stMetricLabel"] p {font-size:.875rem;}
    [data-testid="stMetricValue"] {font-size:1.5rem;font-variant-numeric:tabular-nums;}
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] * {
      white-space:normal !important;overflow-wrap:anywhere;text-overflow:clip !important;height:auto;
    }
    button:focus-visible, a:focus-visible {outline:3px solid #176B5B !important;outline-offset:3px;}
    .st-key-simulation_canvas [data-testid="stElementContainer"]:has(> iframe[data-testid="stIFrame"]) {
      flex:0 0 auto;
      height:clamp(360px,calc(100dvh - 370px),570px);
    }
    .st-key-simulation_canvas iframe[data-testid="stIFrame"] {height:100%;}
    </style>""", unsafe_allow_html=True)


def reset_map_defaults():
    scenario = MAP_SCENARIOS[st.session_state.get("scenario", "single_block")]
    for key, value in (("orders", scenario["n"]), ("pickers", scenario["pickers"]),
                       ("capacity", int(scenario["capacity"])), ("tightness", scenario["tightness"])):
        st.session_state[key] = value


def clear_instance_upload():
    st.session_state.pop("uploaded_instance_bytes", None)
    st.session_state.pop("uploaded_instance_name", None)
    st.session_state["instance_upload_widget_populated"] = False


def remember_instance_upload():
    upload = st.session_state.get("upload")
    if upload is None:
        active = (st.session_state.get("workspace", SIMULATION) == SIMULATION
                  and st.session_state.get("source", UPLOAD) == UPLOAD)
        if active and st.session_state.get("instance_upload_widget_populated", False):
            clear_instance_upload()
        st.session_state["instance_upload_widget_populated"] = False
    else:
        st.session_state["uploaded_instance_bytes"] = upload.getvalue()
        st.session_state["uploaded_instance_name"] = upload.name
        st.session_state["instance_upload_widget_populated"] = True


def reset_hidden_instance_upload():
    if st.session_state.pop("instance_upload_widget_hidden", False):
        st.session_state.pop("upload", None)
        st.session_state["instance_upload_widget_populated"] = False


def sidebar(root, on_run):
    content = None
    with st.sidebar:
        st.subheader("Dữ liệu")
        source_labels = {SYNTHETIC: "Dữ liệu mô phỏng", KRIS: "Bộ dữ liệu Kris", UPLOAD: "Tải dữ liệu JSON"}
        source = st.selectbox("Nguồn dữ liệu", [SYNTHETIC, KRIS, UPLOAD], key="source",
                              format_func=source_labels.get)
        draft = {"source": source}
        if source != UPLOAD:
            st.session_state["instance_upload_widget_populated"] = False
            st.session_state["instance_upload_widget_hidden"] = True

        if st.session_state.get("last_active_source") != source:
            st.session_state["last_active_source"] = source
            st.session_state.pop("snapshot", None)

        if source == SYNTHETIC:
            scenario = st.selectbox("Kịch bản kho", list(MAP_SCENARIOS.keys()),
                                    format_func=MAP_LABELS.get, key="scenario",
                                    help="Kho chuẩn: một khối. Kho 2 khối: một lối ngang giữa kho. "
                                         "Kho lớn: ba khối. Cao điểm: hạn giao gấp. Phân khu ABC: hàng thường lấy ở gần điểm xuất phát.")
            draft["scenario"] = scenario
            scen = MAP_SCENARIOS[scenario]

            if st.session_state.get("last_scenario") != scenario:
                st.session_state["last_scenario"] = scenario
                st.session_state["orders"] = int(scen["n"])
                st.session_state["pickers"] = int(scen["pickers"])
                st.session_state["capacity"] = int(scen["capacity"])
                st.session_state["tightness"] = float(scen["tightness"])
                st.session_state.pop("snapshot", None)
                st.session_state.pop("result_method", None)

            for key, value in (("orders", int(scen["n"])), ("pickers", int(scen["pickers"])),
                               ("capacity", int(scen["capacity"])), ("tightness", float(scen["tightness"]))):
                st.session_state.setdefault(key, value)
            order_column, picker_column = st.columns(2)
            draft["orders"] = order_column.number_input("Số đơn", 1, 300, key="orders")
            draft["pickers"] = picker_column.number_input("Số nhân viên", 1, 12, key="pickers")
            draft["capacity"] = st.number_input("Sức chứa mỗi chuyến (sản phẩm)", 1, 500, key="capacity")

        elif source == KRIS:
            try:
                catalog = json.loads((root / "data/processed/kris_small/catalog.json").read_text(encoding="utf-8"))
                by_file = {r["file"]: r for r in sorted(catalog["instances"], key=lambda r: (r["orders"], r["file"]))}
                if by_file:
                    draft["file"] = st.selectbox("Bộ dữ liệu Kris", list(by_file), key="kris_file",
                        format_func=lambda name: f"{name.split('/')[-1].removesuffix('.json')} · {by_file[name]['orders']} đơn")
                else:
                    st.caption("Chưa có dữ liệu Kris. Bạn có thể chọn dữ liệu mô phỏng.")
            except (OSError, ValueError, KeyError, TypeError):
                st.caption("Không đọc được danh sách dữ liệu Kris. Bạn có thể chọn dữ liệu mô phỏng.")
        else:
            reset_hidden_instance_upload()
            upload = st.file_uploader("Tải dữ liệu đầu vào (JSON)", type=["json"], key="upload",
                                      on_change=remember_instance_upload,
                                      help="Tệp mô tả kho, đơn hàng và nhân viên theo định dạng JSON của dự án.")
            if upload is not None:
                remember_instance_upload()
            else:
                st.session_state["instance_upload_widget_populated"] = False
            content = st.session_state.get("uploaded_instance_bytes")
            if upload is None and content is not None:
                st.caption(f"Tệp đang dùng: {st.session_state.get('uploaded_instance_name', 'JSON đã tải')}")
                st.button("Đóng tệp", key="close_instance_upload", on_click=clear_instance_upload)
            draft["upload_sha256"] = upload_digest(content)

        draft["comparison"] = st.checkbox(
            "So sánh 5 thuật toán: B0, B2, LNS, ALNS, VNS", key="comparison",
            help="B0: gom đơn theo thứ tự rank, đi theo láng giềng gần nhất. "
                 "B2: gom đơn tham lam, cải thiện tuyến bằng 2-opt. "
                 "LNS (Large Neighborhood Search): bỏ rồi chèn lại một phần đơn. "
                 "ALNS (Adaptive Large Neighborhood Search): LNS với cách chọn toán tử thích nghi. "
                 "VNS (Variable Neighborhood Search): thay đổi lân cận đơn hàng, chuyến và lịch nhân viên. "
                 "Cả 5 dùng cùng dữ liệu và trọng số. Ngân sách tìm kiếm áp dụng riêng cho LNS, ALNS và VNS. "
                 "Mặc định chạy B0 và ALNS.",
        )
        draft["vns"] = draft["comparison"]
        st.button("Chạy tối ưu", type="primary", width="stretch", key="run",
                  on_click=on_run, disabled=st.session_state.get("run_status") == "running")
        with st.expander("Nâng cao", expanded=False, key="advanced_options", on_change="rerun") as advanced:
            if advanced.open:
                st.caption("Thay đổi các tùy chọn rồi bấm Chạy tối ưu để áp dụng.")
            if source == SYNTHETIC:
                st.button("Khôi phục mặc định", key="reset_map_defaults", on_click=reset_map_defaults,
                          help="Đặt lại số đơn, nhân viên, sức chứa và hạn giao của kịch bản đang chọn.")
                draft["tightness"] = st.slider("Mức nới hạn giao", .02, 1., step=.01, key="tightness",
                                               help="Giá trị càng nhỏ thì thời hạn giao hàng càng gấp.")
            st.session_state.setdefault("seed", 42)
            st.session_state.setdefault("budget", 2.0)
            draft["seed"] = st.number_input("Seed ngẫu nhiên", min_value=0, key="seed",
                                            help="Giữ cùng seed để tạo lại dữ liệu và cách khởi tạo thuật toán.")
            draft["seconds"] = st.slider("Thời gian tìm kiếm (giây)", .2, 10., step=.2, key="budget",
                                          help="Áp dụng riêng cho từng thuật toán tìm kiếm. Một bước xử lý có thể khiến thời gian thực tế vượt mức này.")
            profile_labels = {"balanced": "Cân bằng", "distance": "Giảm quãng đường",
                              "makespan": "Hoàn tất sớm", "tardiness": "Giảm tổng độ trễ"}
            draft["objective_profile"] = st.selectbox(
                "Ưu tiên tối ưu", list(WEIGHT_PROFILES), key="objective_profile",
                format_func=profile_labels.get,
                help="Ưu tiên tiêu chí được chọn khi tính điểm F. Đơn hàng vẫn có thể bị trễ.")
            draft["candidate_policy"] = st.radio(
                "Cách chọn vị trí chèn", ["uniform", "guided"], key="candidate_policy",
                horizontal=True,
                format_func=lambda policy: "Ngẫu nhiên" if policy == "uniform" else "Có hướng dẫn",
                help="LNS/ALNS: ưu tiên một phần vị trí gần và ít gây trễ, giữ một phần ngẫu nhiên. "
                     "Mỗi vị trí được giữ vẫn tính đầy đủ điểm F; chất lượng phụ thuộc dữ liệu.")
            draft["incremental_validation"] = st.checkbox(
                "Tăng tốc kiểm tra ứng viên", key="incremental_validation",
                help="Tái sử dụng kiểm tra phần kế hoạch không đổi. Nghiệm cuối vẫn được kiểm tra đầy đủ.")

    return draft, content


def instance_summary(instance):
    quantity = sum(sum(order.items.values()) for order in instance.orders)
    st.write(f"**{len(instance.orders)} đơn · {quantity} sản phẩm** · {instance.operations.pickers} nhân viên · "
             f"Sức chứa {instance.operations.capacity:g} {unit_label(instance, 'capacity')} mỗi chuyến")


def figure(fig):
    st.pyplot(fig, width="stretch")
    plt.close(fig)


def route_view(instance, result):
    picker_column, batch_column = st.columns(2)
    picker_options = list(range(1, instance.operations.pickers + 1)) + ["Tất cả"]
    if st.session_state.get("route_picker") not in picker_options:
        st.session_state["route_picker"] = result["batches"][0]["picker"]
    picker = picker_column.selectbox("Nhân viên", picker_options, key="route_picker",
                                     format_func=lambda x: x if x == "Tất cả" else f"Nhân viên {x}")
    batches = [b for b in result["batches"] if picker == "Tất cả" or b["picker"] == picker]
    if batches:
        options = [b["id"] for b in batches] + ["Tất cả"]
        if st.session_state.get("route_batch") not in options:
            st.session_state["route_batch"] = options[0]
        batch = batch_column.selectbox("Chuyến lấy hàng", options, key="route_batch")
        route_figure = warehouse_figure(instance, result, None if picker == "Tất cả" else picker,
                                        None if batch == "Tất cả" else batch)
        route_figure.axes[0].set_title(f"Lộ trình chuyến {batch}" if batch != "Tất cả"
                                      else "Lộ trình lấy hàng của các nhân viên")
        figure(route_figure)
        st.caption("Ô vuông là điểm xuất phát. Số trên tuyến là thứ tự lấy hàng của chuyến đang chọn.")
        if batch != "Tất cả":
            chosen = next(b for b in batches if b["id"] == batch)
            with st.expander("Thứ tự điểm lấy hàng", expanded=False):
                stops = chosen["stops"][1:-1]
                st.dataframe(pd.DataFrame({"Thứ tự": range(1, len(stops) + 1), "Vị trí": stops}),
                             hide_index=True, width="stretch", height=280)
                st.caption("Mỗi chuyến bắt đầu và kết thúc tại điểm xuất phát.")
    else:
        st.info("Nhân viên này không có chuyến được phân công.")
    st.subheader("Lịch làm việc")
    schedule_figure = gantt_figure(instance, result)
    schedule_figure.axes[0].set_title("Lịch làm việc của các nhân viên")
    figure(schedule_figure)
    st.caption("Màu nhân viên nhất quán với bản đồ. Viền đỏ đánh dấu chuyến có đơn trễ.")


def results_view(snapshot):
    raw_snapshot = snapshot
    snapshot = display_snapshot_for_simulation(raw_snapshot)
    instance = Instance.from_dict(snapshot["instance"])
    results = snapshot["results"]
    conversion_caption = kris_conversion_caption(instance)
    scenario = instance.metadata.get("scenario", {})
    scenario_id = scenario.get("id") if isinstance(scenario, dict) else None
    map_name = MAP_LABELS.get(scenario_id, instance.name) if isinstance(scenario_id, str) else instance.name
    names = list(results)
    best_objective = min(result["metrics"]["objective"] for result in results.values())
    best_methods = [name for name in names if math.isclose(
        results[name]["metrics"]["objective"], best_objective, rel_tol=1e-9, abs_tol=1e-12)]
    st.caption(f"{map_name} · {len(instance.orders)} đơn · {instance.operations.pickers} nhân viên · "
               f"seed {snapshot.get('seed', 'không lưu')} · F thấp nhất lần này: {', '.join(best_methods)}" +
               (" · Bản lưu" if snapshot.get("saved_playback") else ""))
    if st.session_state.get("result_method") not in names:
        st.session_state["result_method"] = "ALNS" if "ALNS" in names else names[0]
    method_column, export_column = st.columns([3, 2], vertical_alignment="bottom")
    selected = method_column.selectbox(
        "Phương án đang xem", names, key="result_method",
        help=f"{', '.join(best_methods)} có F thấp nhất ({best_objective:.4f}) trong lần chạy này. "
             "F thấp hơn chưa chắc mọi chỉ số đều tốt hơn; đây không phải kết luận cho mọi dữ liệu.")
    result = results[selected]
    with export_column.expander("Tải kết quả", expanded=False):
        for label, data, filename in [
            ("Tải phương án (JSON)", raw_snapshot['results'][selected], f"{selected}-solution.json"),
            ("Tải dữ liệu đầu vào (JSON)", raw_snapshot['instance'], "warehouse-instance.json"),
            ("Tải toàn bộ lần chạy (JSON)", raw_snapshot, "warehouse-snapshot.json"),
        ]:
            st.download_button(label, json.dumps(data, ensure_ascii=False, indent=2),
                               file_name=filename, mime="application/json", key=filename)
    time_unit, distance_unit = unit_label(instance, "time"), unit_label(instance, "distance")
    time_scale = time_scale_seconds(instance)
    metrics, baseline = result["metrics"], results["B0"]["metrics"]
    col1, col2, col3 = st.columns(3)
    col1.metric("Đơn trễ", f"{metrics['late_orders']} đơn")

    time_display = format_duration(metrics["makespan"], instance)
    if time_scale is not None:
        col2.metric("Thời gian hoàn tất", time_display,
                    help=conversion_caption or
                         f"Quy đổi theo {time_scale:g} giây cho mỗi đơn vị thời gian đã khai báo")
        col3.metric("Quãng đường", f"{metrics['distance']:,.1f} {distance_unit}")
    else:
        col2.metric("Thời gian hoàn tất", time_display,
                    delta="Không quy đổi đơn vị nguồn", delta_color="off")
        col3.metric("Quãng đường", f"{metrics['distance']:,.1f} {distance_unit}")
    if conversion_caption:
        st.caption("Kris dùng quy ước đơn vị mô phỏng; hệ số nằm ở trợ giúp Thời gian hoàn tất. JSON giữ dữ liệu gốc.")
    elif instance.metadata.get("source_kind") == "author_benchmark":
        st.caption("Đang xem đơn vị nguồn; thời gian vận hành khác thời gian chạy thuật toán.")
    sim_tab, overview, routes, details, evaluation = st.tabs(
        ["Mô phỏng", "Tổng quan", "Tuyến và lịch", "Chi tiết", "Đánh giá"],
        key="result_tabs", on_change="rerun")
    with sim_tab:
        if sim_tab.open:
            with st.container(key="simulation_canvas"):
                render_simulation(instance, result, height=560)
    with overview:
        if overview.open:
            st.subheader("Kết quả của phương án")
            st.write(f"Đã phân công **{metrics['batches']} chuyến** cho **{metrics['used_pickers']} nhân viên**. "
                     f"**{len(instance.orders) - metrics['late_orders']}/{len(instance.orders)} đơn** hoàn thành đúng hạn.")
            pct = improvement(metrics["distance"], baseline["distance"])
            if selected != "B0":
                if pct is None:
                    st.write("Quãng đường B0 bằng 0, không tính phần trăm thay đổi.")
                else:
                    direction = "giảm" if pct >= 0 else "tăng"
                    st.write(f"Quãng đường {direction} **{abs(pct):.1f}%** so với phương án cơ sở B0.")
            st.caption("Bài toán cho phép giao trễ và tính độ trễ vào điểm F. Phương án đã được kiểm tra sức chứa, tuyến đi và lịch làm việc.")
            if time_scale is None:
                st.caption("Dữ liệu giữ nguyên đơn vị nguồn; chưa quy đổi sang giây/phút.")
    if routes.open:
        with routes:
            route_view(instance, result)
    if evaluation.open:
        with evaluation:
            current_run_view(raw_snapshot, selected)
    with details:
        if details.open:
            late_only = st.checkbox("Chỉ xem đơn trễ", key="late_only")
            rows = [r for r in result["orders"] if not late_only or r["tardiness"] > 1e-9]
            st.subheader("Đơn hàng")
            st.dataframe(pd.DataFrame(rows, columns=["id", "batch", "picker", "due", "completion", "tardiness"]).rename(columns={
                "id": "Đơn", "batch": "Chuyến", "picker": "Nhân viên", "due": f"Hạn ({time_unit})",
                "completion": f"Hoàn tất ({time_unit})", "tardiness": f"Trễ ({time_unit})"}),
                         hide_index=True, width="stretch", height=320)
            st.subheader("Chuyến lấy hàng")
            cols = {"id": "Chuyến", "picker": "Nhân viên", "orders": "Các đơn", "load": f"Tải ({unit_label(instance, 'capacity')})",
                    "distance": f"Quãng đường ({distance_unit})", "start": f"Bắt đầu ({time_unit})", "end": f"Kết thúc ({time_unit})"}
            st.dataframe(pd.DataFrame([{k: b[k] for k in cols} for b in result["batches"]]).rename(columns=cols),
                         hide_index=True, width="stretch", height=280)

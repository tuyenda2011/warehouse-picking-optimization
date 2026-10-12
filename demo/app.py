"""Run from project root: python -m streamlit run demo/app.py."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st

from demo.components import instance_summary, results_view, sidebar, style
from demo.evaluation import BENCHMARK, SIMULATION, benchmark_workspace
from demo.state import (
    fail_run,
    finish_run,
    is_stale,
    prepare_instance,
    run_scenario,
    start_run,
)
from src.demo_snapshot import validate_snapshot
from src.models import Instance

st.set_page_config(page_title="Tối ưu lấy hàng", page_icon="📦", layout="wide")
style()


def begin():
    start_run(st.session_state)


@st.cache_data(show_spinner=False, max_entries=8)
def prepared(draft, content):
    return prepare_instance(draft, ROOT, content).to_dict()


# Keep draft controls and result filters when another workspace hides their widgets.
for control in ("source", "scenario", "orders", "pickers", "capacity", "tightness", "seed", "budget",
                "objective_profile", "candidate_policy", "incremental_validation", "comparison", "kris_file", "result_method", "route_picker", "route_batch",
                "late_only", "objective_reference", "result_tabs", "advanced_options",
                "evaluation_local", "evaluation_group",
                "evaluation_reference", "evaluation_style", "evaluation_figure", "benchmark_tabs"):
    if control in st.session_state:
        st.session_state[control] = st.session_state[control]
workspace = st.sidebar.radio("Chức năng", [SIMULATION, BENCHMARK], key="workspace", horizontal=True)
if workspace == BENCHMARK:
    st.session_state["instance_upload_widget_populated"] = False
    st.session_state["instance_upload_widget_hidden"] = True
    benchmark_workspace(ROOT)
    st.stop()

st.session_state["benchmark_upload_widget_populated"] = False
st.session_state["benchmark_upload_widget_hidden"] = True
draft, content = sidebar(ROOT, begin)
st.title("Tối ưu lấy hàng")

if st.session_state.get("run_status") == "running":
    progress = st.progress(0, text="Đang kiểm tra dữ liệu...")
    try:
        instance = Instance.from_dict(prepared(draft, content))
        snapshot = run_scenario(instance, draft, lambda value, text: progress.progress(value, text=text))
        finish_run(st.session_state, snapshot)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        fail_run(st.session_state, exc)
    progress.empty()
    st.rerun()

saved = ROOT / "results/demo_vns/snapshot.json"
if saved.is_file():
    with st.sidebar:
        if st.button("Mở lần chạy đã lưu", key="open_saved"):
            try:
                snapshot = validate_snapshot(json.loads(saved.read_text(encoding="utf-8")))
                start_run(st.session_state)
                finish_run(st.session_state, {**snapshot, "saved_playback": True})
                st.rerun()
            except (OSError, ValueError, KeyError, TypeError) as exc:
                fail_run(st.session_state, exc)

if st.session_state.get("run_status") == "error":
    st.error("Không thể chạy thuật toán. Hãy kiểm tra dữ liệu và thông số đã chọn.")
    with st.expander("Chi tiết lỗi", expanded=False):
        st.code(st.session_state["run_error"], language=None)

snapshot = st.session_state.get("snapshot")
if snapshot:
    if is_stale(snapshot, draft):
        st.info("Cấu hình bên trái chưa được áp dụng. Bấm Chạy tối ưu để cập nhật.")
    results_view(snapshot)
else:
    try:
        instance = Instance.from_dict(prepared(draft, content))
        instance_summary(instance)
    except (OSError, ValueError, KeyError, TypeError):
        st.write("Chọn dữ liệu trong thanh bên để bắt đầu.")
    st.caption("Chọn dữ liệu ở thanh bên rồi bấm Chạy tối ưu.")

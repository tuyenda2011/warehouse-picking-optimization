"""Verify laptop layouts and display-only Kris units in isolated Edge."""
import argparse
import csv
from dataclasses import asdict
import hashlib
import io
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import expect, sync_playwright

from demo.display import display_snapshot_for_simulation, kris_convention
from src.demo_snapshot import validate_snapshot
from src.evaluation import make_evaluation
from src.models import Instance, read_instance
from src.search import SearchConfig
from src.solver import solve
from src.units import format_duration


def main():
    expect.set_options(timeout=45000)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8518")
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/streamlit-laptop-20261011/browser")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"browser": "isolated headless system Edge", "layouts": [], "flows": [], "page_errors": []}
    instance = read_instance(ROOT / "data/processed/kris_small/instances_106_1.json")
    config = SearchConfig(seconds=0, iterations=3)
    payload = make_evaluation([{
        "name": "kris", "config": {"methods": ["B0", "B2"], "search_seeds": [7], "search": asdict(config)},
        "instances": [instance.to_dict()], "results": [solve(instance, method, 7, config) for method in ("B0", "B2")],
    }], preset="quick")
    fixture = output / "evaluation.json"
    fixture.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf8")
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 768}, accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(45000)
        page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))

        def settled():
            expect(page.locator('[data-testid="stApp"][data-test-script-state="notRunning"]')).to_be_visible()
            expect(page.get_by_test_id("stSkeleton")).to_have_count(0)
            expect(page.get_by_test_id("stException")).to_have_count(0)
            expect(page.locator('[data-stale="true"]')).to_have_count(0)

        def select(key, value):
            settled()
            widget = page.locator(f".st-key-{key}")
            widget.get_by_role("button", name="Open", exact=True).click()
            page.get_by_role("option", name=value, exact=True).click()
            expect(widget.get_by_role("combobox")).to_have_value(value)
            settled()

        def tab(name):
            item = page.get_by_role("tab", name=name, exact=True)
            item.click()
            expect(item).to_have_attribute("aria-selected", "true")
            ready = {"Mô phỏng": 'iframe[data-testid="stIFrame"]', "Chi tiết": ".st-key-late_only",
                     "Tuyến và lịch": ".st-key-route_picker", "Đánh giá": ".st-key-objective_reference",
                     "Tổng hợp": ".st-key-download_benchmark_summary",
                     "Từng bài toán": ".st-key-download_benchmark_per_instance", "Biểu đồ": ".st-key-evaluation_figure"}
            expect(page.locator(ready[name]).first).to_be_visible()
            settled()

        def download(label, filename):
            with page.expect_download() as pending:
                page.get_by_role("button", name=label, exact=True).click()
            target = output / filename
            pending.value.save_as(target)
            settled()
            return target

        def snapshot(filename):
            panel = page.get_by_test_id("stExpander").filter(has=page.get_by_text("Tải kết quả", exact=True))
            panel.locator("summary").click()
            target = download("Tải toàn bộ lần chạy (JSON)", filename)
            panel.locator("summary").click()
            return validate_snapshot(json.loads(target.read_text(encoding="utf8")))

        def layout(name, width, height):
            page.set_viewport_size({"width": width, "height": height})
            page.get_by_test_id("stMain").evaluate("el => el.scrollTo(0, 0)")
            settled()
            frame = page.frame_locator('iframe[data-testid="stIFrame"]').first
            expect(frame.locator("#simCanvas")).to_be_visible()
            expect(frame.locator("#timeBadge")).to_be_visible()
            bounds = page.locator('iframe[data-testid="stIFrame"]').first.bounding_box()
            canvas = frame.locator("#simCanvas").bounding_box()
            heading = page.get_by_role("heading", name="Tối ưu lấy hàng", exact=True).bounding_box()
            header = page.get_by_test_id("stHeader").bounding_box()
            assert heading["y"] >= header["y"] + header["height"], (heading, header)
            assert canvas["height"] >= 200, canvas
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert frame.locator("body").evaluate("el => el.scrollWidth <= el.clientWidth")
            clipped = page.get_by_test_id("stMetricValue").evaluate_all(
                "els => els.flatMap(el => [el, ...el.querySelectorAll('*')]).filter(el => el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent)")
            assert not clipped, clipped
            run_bounds = page.locator(".st-key-run").bounding_box()
            assert 0 <= run_bounds["y"] < height - 32, run_bounds
            comparison_bounds = page.locator(".st-key-comparison").bounding_box()
            assert comparison_bounds["y"] + comparison_bounds["height"] <= run_bounds["y"], comparison_bounds
            page.screenshot(path=str(output / f"{name}-{width}x{height}.png"))
            page.locator('iframe[data-testid="stIFrame"]').first.screenshot(path=str(output / f"{name}-replay-{width}x{height}.png"))
            evidence["layouts"].append({"case": name, "width": width, "height": height, "heading": heading, "iframe": bounds, "canvas": canvas, "run": run_bounds})

        try:
            page.goto(args.url, wait_until="domcontentloaded")
            expect(page.locator(".st-key-run")).to_be_visible()
            expect(page.locator(".st-key-display_unit_mode")).to_have_count(0)
            expect(page.get_by_role("checkbox", name="Dùng đơn vị mô phỏng", exact=True)).to_have_count(0)
            comparison = page.get_by_role("checkbox", name="So sánh 5 thuật toán: B0, B2, LNS, ALNS, VNS", exact=True)
            expect(comparison).to_be_visible()
            assert page.locator(".st-key-comparison").evaluate("el => !el.closest('[data-testid=\"stExpander\"]')")
            page.get_by_text("Nâng cao", exact=True).click()
            budget = page.locator(".st-key-budget").get_by_role("slider")
            budget.focus()
            budget.press("Home")
            expect(budget).to_have_value("0.2")
            settled()
            page.get_by_text("Nâng cao", exact=True).click()
            page.locator(".st-key-run").get_by_role("button").click()
            expect(page.locator(".st-key-result_method")).to_be_visible()
            settled()
            assert page.get_by_test_id("stDataFrame").count() == 0
            for width, height in ((1366, 768), (1440, 900)):
                layout("synthetic", width, height)
            evidence["flows"].append("synthetic; lazy default tab; laptop fit")

            select("source", "Bộ dữ liệu Kris")
            page.locator(".st-key-comparison").get_by_text(
                "So sánh 5 thuật toán: B0, B2, LNS, ALNS, VNS", exact=True).click()
            expect(comparison).to_be_checked()
            settled()
            page.locator(".st-key-run").get_by_role("button").click()
            expect(page.locator(".st-key-result_method")).to_be_visible()
            settled()
            raw = snapshot("kris-before.json")
            assert list(raw["results"]) == ["B0", "B2", "LNS", "ALNS", "VNS"]
            convention = kris_convention(raw["instance"])
            time_factor = convention["seconds_per_source_time"] / 60
            selected = page.locator(".st-key-result_method").get_by_role("combobox").input_value()
            metrics = raw["results"][selected]["metrics"]
            for width, height in ((1366, 768), (1440, 900)):
                layout("kris", width, height)
            frame = page.frame_locator('iframe[data-testid="stIFrame"]').first
            maximum = float(frame.locator("#timelineSlider").get_attribute("max"))
            assert math.isclose(maximum, metrics["makespan"] * time_factor)
            frame.locator("#playBtn").click()
            frame.locator("#resetBtn").click()
            frame.locator("#timelineSlider").evaluate("el => {el.value=el.max; el.dispatchEvent(new Event('input',{bubbles:true}));}")
            display_instance = Instance.from_dict(display_snapshot_for_simulation(raw)["instance"])
            assert format_duration(maximum, display_instance) in frame.locator("#timeBadge").get_attribute("title")
            frame.locator('[data-speed="2"]').click()
            frame.locator("#zoomInBtn").click()
            tab("Chi tiết")
            page.get_by_text("Chỉ xem đơn trễ", exact=True).click()
            settled()
            tab("Tuyến và lịch")
            assert page.locator(".st-key-route_picker").is_visible()
            assert page.locator(".st-key-route_batch").is_visible()
            tab("Chi tiết")
            expect(page.get_by_role("checkbox", name="Chỉ xem đơn trễ", exact=True)).to_be_checked()
            tab("Đánh giá")
            expect(page.get_by_text("Chỉ số dùng cùng quy ước minh họa với mô phỏng", exact=False)).to_be_visible()
            tab("Mô phỏng")
            frame = page.frame_locator('iframe[data-testid="stIFrame"]').first
            assert math.isclose(float(frame.locator("#timelineSlider").get_attribute("max")), metrics["makespan"] * time_factor)
            assert "đơn vị thời gian nguồn" not in frame.locator("#timeBadge").inner_text()
            after = snapshot("kris-after.json")
            assert after == raw
            evidence["flows"].append("Kris; fixed simulation units; operational clock; playback controls; tab filters; unchanged raw JSON")

            page.get_by_text("Đánh giá benchmark", exact=True).click()
            expect(page.locator(".st-key-evaluation_upload")).to_be_visible()
            page.locator('.st-key-evaluation_upload input[type="file"]').set_input_files(str(fixture))
            expect(page.get_by_role("tab", name="Tổng hợp", exact=True)).to_be_visible()
            settled()
            assert page.get_by_test_id("stImage").count() == 0
            tab("Từng bài toán")
            scaled_file = download("Tải bảng từng bài toán theo mô phỏng (CSV)", "display.csv")
            native_file = download("Tải bảng từng bài toán đơn vị gốc (CSV)", "native.csv")
            scaled_rows = list(csv.DictReader(io.StringIO(scaled_file.read_text(encoding="utf-8-sig"))))
            native_rows = list(csv.DictReader(io.StringIO(native_file.read_text(encoding="utf-8-sig"))))
            native_results = {result["method"]: result for result in payload["groups"][0]["results"]}
            assert {row["method"] for row in native_rows} == set(native_results)
            for native, scaled in zip(native_rows, scaled_rows, strict=True):
                original = native_results[native["method"]]
                assert scaled["time_unit"] == "phút" and scaled["distance_unit"] == "m"
                assert native["time_unit"] == "đơn vị thời gian nguồn"
                assert native["distance_unit"] == "đơn vị khoảng cách nguồn"
                assert native["objective_mean"] == scaled["objective_mean"]
                assert native["total_seconds_mean"] == scaled["total_seconds_mean"]
                assert math.isclose(float(native["objective_mean"]), original["metrics"]["objective"])
                assert math.isclose(float(native["makespan_mean"]), original["metrics"]["makespan"])
                assert math.isclose(float(native["distance_mean"]), original["metrics"]["distance"])
                assert math.isclose(float(native["tardiness_mean"]), original["metrics"]["tardiness"])
                assert math.isclose(float(native["total_seconds_mean"]), original["timing"]["total_seconds"])
                assert math.isclose(float(scaled["makespan_mean"]), float(native["makespan_mean"]) * time_factor)
                assert math.isclose(float(scaled["distance_mean"]), float(native["distance_mean"]) * .1)
            tab("Biểu đồ")
            select("evaluation_figure", f"Chỉ số vận hành · {instance.name}")
            expect(page.get_by_test_id("stImage")).to_have_count(1)
            display_png = download("Tải hình PNG", "operations-display.png")
            display_src = page.get_by_test_id("stImage").locator("img").get_attribute("src")
            expect(page.locator(".st-key-display_unit_mode")).to_have_count(0)
            expect(page.get_by_role("tab", name="Biểu đồ", exact=True)).to_have_attribute("aria-selected", "true")
            expect(page.locator(".st-key-evaluation_figure").get_by_role("combobox")).to_have_value(f"Chỉ số vận hành · {instance.name}")
            assert display_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
            page.screenshot(path=str(output / "benchmark-simulation.png"))
            page.get_by_text("Mô phỏng", exact=True).first.click()
            expect(page.locator(".st-key-result_method")).to_be_visible()
            settled()
            assert snapshot("kris-workspace-return.json") == raw
            expect(page.locator(".st-key-display_unit_mode")).to_have_count(0)
            page.get_by_text("Đánh giá benchmark", exact=True).click()
            expect(page.get_by_role("tab", name="Biểu đồ", exact=True)).to_be_visible()
            settled()
            expect(page.locator(".st-key-evaluation_figure").get_by_role("combobox")).to_have_value(f"Chỉ số vận hành · {instance.name}")
            expect(page.get_by_test_id("stImage").locator("img")).to_have_attribute("src", display_src)
            return_png = download("Tải hình PNG", "operations-display-return.png")
            assert return_png.read_bytes() == display_png.read_bytes()
            bad = output / "invalid.json"
            bad.write_text('{"kind":"bad"}', encoding="utf8")
            page.locator('.st-key-evaluation_upload input[type="file"]').set_input_files(str(bad))
            expect(page.get_by_text("Tệp đánh giá không hợp lệ", exact=False)).to_be_visible()
            assert page.get_by_test_id("stImage").count() == 0
            assert page.get_by_test_id("stDataFrame").count() == 0
            evidence["flows"].append("benchmark; simulation view and PNG; native/display CSV audited against source; lazy tabs; selected chart and workspace state; invalid replacement clears old evidence")
            page.get_by_text("Mô phỏng", exact=True).first.click()
            expect(page.locator(".st-key-run")).to_be_visible()
            select("source", "Tải dữ liệu JSON")
            warehouse = output / "warehouse.json"
            warehouse.write_text(json.dumps(instance.to_dict()), encoding="utf8")
            page.locator('.st-key-upload input[type="file"]').set_input_files(str(warehouse))
            expect(page.get_by_role("button", name="Remove warehouse.json", exact=True)).to_be_visible()
            page.locator(".st-key-run").get_by_role("button").click()
            expect(page.locator(".st-key-result_method")).to_be_visible()
            uploaded = snapshot("uploaded-before.json")
            page.get_by_text("Đánh giá benchmark", exact=True).click()
            expect(page.get_by_text("Tệp đánh giá không hợp lệ", exact=False)).to_be_visible()
            page.get_by_text("Mô phỏng", exact=True).first.click()
            expect(page.locator(".st-key-result_method")).to_be_visible()
            assert snapshot("uploaded-return.json") == uploaded
            expect(page.get_by_text("Tệp đang dùng: warehouse.json", exact=True)).to_be_visible()
            page.locator(".st-key-run").get_by_role("button").click()
            expect(page.locator(".st-key-result_method")).to_be_visible()
            settled()
            rerun = snapshot("uploaded-rerun.json")
            assert rerun["instance"] == uploaded["instance"]
            assert rerun["draft"]["upload_sha256"] == uploaded["draft"]["upload_sha256"]
            page.get_by_role("button", name="Đóng tệp", exact=True).click()
            page.locator(".st-key-run").get_by_role("button").click()
            expect(page.get_by_text("Không thể chạy thuật toán", exact=False)).to_be_visible()
            expect(page.locator(".st-key-result_method")).to_have_count(0)
            page.locator('.st-key-upload input[type="file"]').set_input_files(str(warehouse))
            expect(page.get_by_role("button", name="Remove warehouse.json", exact=True)).to_be_visible()
            page.get_by_role("button", name="Remove warehouse.json", exact=True).click()
            expect(page.get_by_text("Chọn dữ liệu trong thanh bên để bắt đầu.", exact=True)).to_be_visible()
            expect(page.locator(".st-key-close_instance_upload")).to_have_count(0)
            evidence["flows"].append("uploaded input survives workspace changes and can rerun; explicit close removes input and prevents stale results")
            assert not evidence["page_errors"], evidence["page_errors"]
            evidence["passed"] = True
        except Exception as error:
            evidence.update(passed=False, error=str(error))
            page.screenshot(path=str(output / "failure.png"))
            raise
        finally:
            context.close()
            browser.close()
            evidence["artifacts_sha256"] = {item.name: hashlib.sha256(item.read_bytes()).hexdigest()
                                            for item in sorted(output.iterdir()) if item.is_file() and item.name != "verification.json"}
            (output / "verification.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

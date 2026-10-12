"""Check declared units, weighted loads, and replay clocks in the real demo UI."""
import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import expect, sync_playwright

from demo.display import display_snapshot_for_simulation, kris_convention
from src.demo_snapshot import validate_snapshot
from src.generator import generate
from src.models import Order, Product
from src.units import format_duration, time_scale_seconds
from src.validator import validate_solution


CASES = (
    ("minute_subunit", "minute", .25, "0 phút 15 giây"),
    ("second", "second", 1.25, "0 phút 01 giây"),
    ("second_half_up", "seconds", .5, "0 phút 01 giây"),
    ("hour_subunit", "hour", .125, "7 phút 30 giây"),
    ("hour_with_seconds", "hours", 1.125, "1 giờ 07 phút 30 giây"),
    ("minute_hour_boundary", "minute", 59.995, "1 giờ 00 phút 00 giây"),
    ("unknown", "warehouse_tick", .5, None),
    ("source_units", "source_time_unit", .5, None),
    ("zero_duration", "minute", 0., "0 phút 00 giây"),
)


def fixture(name, time_unit, duration):
    base = generate(n=1, seed=42, pickers=1, capacity=10., aisles=1, rows=1)
    instance = replace(
        base,
        name=f"display-units-{name}",
        nodes=[base.nodes[0]],
        edges=[],
        products=[Product("WEIGHTED-SKU", base.depot, size=2.5, pick_minutes=duration)],
        orders=[Order("ONE-ITEM", {"WEIGHTED-SKU": 1}, duration + 10., 0)],
        operations=replace(base.operations, location_minutes=0., batch_minutes=0., speed=1.),
        metadata={
            "source": "browser-regression-fixture",
            "units": {"distance": "metre", "time": time_unit, "capacity": "kg"},
        },
    )
    return instance.validate()


def numeric_value(text):
    match = re.search(r"[-+]?\d[\d,.]*(?:e[-+]?\d+)?", text, flags=re.IGNORECASE)
    assert match, text
    return float(match.group().replace(",", ""))


def compact_clock(value, seconds_per_unit):
    total = max(0, math.floor(value * seconds_per_unit + .5))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8518")
    parser.add_argument("--output", default="tmp/laptop-display-units-20261011")
    parser.add_argument("--kris-only", action="store_true")
    args = parser.parse_args()
    output = ROOT / args.output
    fixture_dir = output / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    records, errors, tiny_midpoints = [], [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url)
        expect(page.locator(".st-key-run").get_by_role("button")).to_be_visible(timeout=45000)
        expect(page.locator(".st-key-display_unit_mode")).to_have_count(0)
        expect(page.get_by_role("checkbox", name="Dùng đơn vị mô phỏng", exact=True)).to_have_count(0)

        def settled():
            expect(page.get_by_test_id("stStatusWidget")).to_have_count(0, timeout=45000)
            expect(page.get_by_test_id("stSkeleton")).to_have_count(0)
            expect(page.get_by_test_id("stException")).to_have_count(0)

        def select(key, value):
            settled()
            widget = page.locator(f".st-key-{key}")
            control = widget.get_by_role("combobox")
            control.press("Escape")
            widget.get_by_role("button", name="Open", exact=True).click()
            option = page.get_by_role("option", name=value, exact=True)
            expect(option).to_be_visible(timeout=15000)
            option.click()
            expect(control).to_have_value(value)
            settled()

        def run(name):
            page.locator(".st-key-run").get_by_role("button").click()
            expect(page.get_by_text(f"{name} ·", exact=False)).to_be_visible(timeout=45000)
            expect(page.locator(".st-key-result_method")).to_be_visible(timeout=45000)
            expect(page.get_by_test_id("stMetric")).to_have_count(3, timeout=45000)
            settled()
            assert snapshot(f"{name}-run")["instance"]["name"] == name

        def snapshot(name):
            page.get_by_text("Tải kết quả", exact=True).click()
            with page.expect_download() as download:
                page.get_by_role("button", name="Tải toàn bộ lần chạy (JSON)", exact=True).click()
            path = output / f"{name}-snapshot.json"
            download.value.save_as(path)
            data = validate_snapshot(json.loads(path.read_text(encoding="utf-8")))
            settled()
            page.get_by_text("Tải kết quả", exact=True).click()
            settled()
            return data

        def simulation():
            page.get_by_role("tab", name="Mô phỏng", exact=True).click()
            settled()
            frame = page.frame_locator(".st-key-simulation_canvas iframe")
            expect(frame.locator("#timelineSlider")).to_be_visible(timeout=15000)
            frame.locator("#resetBtn").click()
            return frame

        def seek(frame, value):
            frame.locator("#timelineSlider").evaluate(
                "(el, value) => { el.value = value; el.dispatchEvent(new Event('input', {bubbles: true})); }",
                value,
            )

        def responsive_screenshots(name, frame):
            page.get_by_test_id("stMetric").nth(1).scroll_into_view_if_needed()
            page.screenshot(path=str(output / f"{name}-desktop.png"), full_page=True)
            page.locator(".st-key-simulation_canvas iframe").screenshot(path=str(output / f"{name}-desktop-replay.png"))
            page.set_viewport_size({"width": 1366, "height": 768})
            expect(page.locator(".st-key-run").get_by_role("button")).to_be_visible()
            page.get_by_test_id("stMetric").nth(1).scroll_into_view_if_needed()
            page.screenshot(path=str(output / f"{name}-laptop.png"), full_page=True)
            page.locator(".st-key-simulation_canvas iframe").screenshot(path=str(output / f"{name}-laptop-replay.png"))
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert frame.locator("body").evaluate("el => el.scrollWidth <= el.clientWidth")
            metric_layout = page.get_by_test_id("stMetric").nth(1).get_by_test_id("stMetricValue").evaluate(
                "el => [el, ...el.querySelectorAll('*')].filter(node => node.clientWidth > 0).map(node => ({"
                "text: node.textContent, client_width: node.clientWidth, scroll_width: node.scrollWidth, "
                "white_space: getComputedStyle(node).whiteSpace, text_overflow: getComputedStyle(node).textOverflow}))"
            )
            (output / f"{name}-laptop-layout.json").write_text(json.dumps(metric_layout, ensure_ascii=False, indent=2), encoding="utf-8")
            assert all(row["scroll_width"] <= row["client_width"] for row in metric_layout), (name, metric_layout)
            page.set_viewport_size({"width": 1440, "height": 900})
            page.wait_for_function("document.querySelector('[data-testid=stSidebar]').getBoundingClientRect().left >= 0")

        select("source", "Tải dữ liệu JSON")
        expect(page.locator(".st-key-upload")).to_be_visible()
        expect(page.locator(".st-key-orders")).to_have_count(0)
        expect(page.get_by_text("Nâng cao", exact=True)).to_have_count(1)
        page.get_by_text("Nâng cao", exact=True).click()
        budget = page.locator(".st-key-budget").get_by_role("slider")
        budget.focus()
        budget.press("Home")
        expect(budget).to_have_value("0.2")
        settled()

        for name, time_unit, duration, physical_text in (() if args.kris_only else CASES):
            instance = fixture(name, time_unit, duration)
            fixture_path = fixture_dir / f"{name}.json"
            fixture_path.write_text(json.dumps(instance.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            page.locator('.st-key-upload input[type="file"]').set_input_files(str(fixture_path))
            expect(page.get_by_role("button", name=f"Remove {fixture_path.name}", exact=True)).to_be_visible()
            settled()
            run(instance.name)
            data = snapshot(name)
            result = data["results"]["ALNS"]
            assert math.isclose(result["metrics"]["makespan"], duration, rel_tol=1e-12, abs_tol=1e-12)
            assert data["instance"] == instance.to_dict()
            assert not validate_solution(instance, result)
            header = page.get_by_test_id("stMetric").nth(1).get_by_test_id("stMetricValue").inner_text()
            frame = simulation()
            slider = frame.locator("#timelineSlider")
            slider_max = float(slider.get_attribute("max"))
            assert math.isclose(slider_max, duration, rel_tol=1e-12, abs_tol=1e-12), (name, slider_max, duration)
            seek(frame, duration)
            badge = frame.locator("#timeBadge").inner_text()
            if physical_text is not None:
                assert header == physical_text, (name, header, physical_text)
                expected_clock = compact_clock(duration, time_scale_seconds(instance))
                assert badge == f"{expected_clock} / {expected_clock}", (name, badge, expected_clock)
                assert frame.locator("#timeBadge").get_attribute("title") == (
                    f"Thời gian vận hành: {physical_text} / {physical_text}")
            else:
                label = "đơn vị thời gian nguồn" if time_unit == "source_time_unit" else time_unit
                assert label in header and math.isclose(numeric_value(header), duration)
                assert badge.count(label) == 1, (name, badge)
                assert math.isclose(numeric_value(badge.split("/")[-1]), duration)
                assert not any(word in badge or word in header for word in ("phút", "giây", "giờ"))

            load_text = status_text = None
            if duration > 0:
                seek(frame, duration / 2)
                load_text = frame.locator("#card-load-p1").inner_text()
                status_text = frame.locator("#card-status-p1").inner_text()
                assert re.search(r"Tải:\s+2\.5\s*/\s*10(?:\.0)?\s+kg", load_text), (name, load_text)
                assert re.search(r"Lấy\s+1\s+sản phẩm", status_text), (name, status_text)
                payload = slider.evaluate("() => simData")
                picking = [segment for segment in payload["pickers"][0]["segments"] if segment["state"] == "picking"]
                assert picking and picking[0]["pick_qty"] == 1 and picking[0]["load"] == 2.5
            else:
                expect(frame.locator("#card-status-p1")).to_have_text("Đã hoàn thành công việc")
                frame.locator("#playBtn").click()
                expect(slider).to_have_value("0")
                assert "NaN" not in frame.locator("body").inner_text()
                tiny_midpoints = slider.evaluate("""() => {
                    const picker = {segments: [
                        {t_start: 0, t_end: 0.00005, x1: 0, y1: 0, x2: 10, y2: 0,
                         state: 'traveling', load: 0, info: 'outbound'},
                        {t_start: 0.00005, t_end: 0.0001, x1: 10, y1: 0, x2: 0, y2: 0,
                         state: 'traveling', load: 0, info: 'return'}
                    ]};
                    return [getPickerState(picker, 0.000025).x, getPickerState(picker, 0.000075).x];
                }""")
                assert all(math.isclose(value, 5., abs_tol=1e-9) for value in tiny_midpoints), tiny_midpoints

            if name in ("minute_subunit", "source_units", "zero_duration"):
                responsive_screenshots(name, frame)
            records.append({"case": name, "time_unit": time_unit, "raw_makespan": duration,
                            "header": header, "badge_at_end": badge, "slider_max": slider_max,
                            "load_during_pick": load_text, "picking_info": status_text})
            print(f"PASS {name}", flush=True)

        select("source", "Bộ dữ liệu Kris")
        expect(page.locator(".st-key-kris_file")).to_be_visible()
        expect(page.locator(".st-key-upload")).to_have_count(0)
        run("Kris-instances_106_1")
        kris = snapshot("kris")
        result = kris["results"]["ALNS"]
        raw = result["metrics"]["makespan"]
        assert kris["instance"]["metadata"]["units"]["time"] == "source_time_unit"
        view = display_snapshot_for_simulation(kris)
        from src.models import Instance
        display_instance = Instance.from_dict(view['instance'])
        converted = view['results']['ALNS']['metrics']
        header = page.get_by_test_id("stMetric").nth(1).get_by_test_id("stMetricValue").inner_text()
        expected_duration = format_duration(converted['makespan'], display_instance)
        assert header == expected_duration, (header, expected_duration)
        distance = page.get_by_test_id('stMetric').nth(2).get_by_test_id('stMetricValue').inner_text()
        assert distance == f"{converted['distance']:,.1f} m"
        expect(page.get_by_text('Kris dùng quy ước đơn vị mô phỏng', exact=False)).to_be_visible()
        expect(page.get_by_test_id('stMetricDelta')).to_have_count(0)
        frame = simulation()
        maximum = float(frame.locator("#timelineSlider").get_attribute("max"))
        convention = kris_convention(kris["instance"])
        assert math.isclose(maximum, raw * convention["seconds_per_source_time"] / 60)
        seek(frame, maximum)
        badge = frame.locator("#timeBadge").inner_text()
        expected_clock = compact_clock(converted["makespan"], 60)
        assert badge == f"{expected_clock} / {expected_clock}", (badge, expected_clock)
        assert frame.locator("#timeBadge").get_attribute("title") == (
            f"Thời gian vận hành: {expected_duration} / {expected_duration}")
        assert 'đơn vị thời gian nguồn' not in badge
        payload = frame.locator('#timelineSlider').evaluate('() => simData')
        assert payload['time_scale_seconds'] == 60
        assert math.isclose(payload['total_distance'], converted['distance'])
        responsive_screenshots("kris", frame)
        records.append({"case": "actual_kris", "raw_makespan": raw, "header": header,
                        "distance": distance, "badge_at_end": badge, "slider_max": maximum,
                        "convention": convention})
        expect(page.locator(".st-key-display_unit_mode")).to_have_count(0)
        assert snapshot("kris-fixed-simulation-view") == kris
        records[-1]["raw_snapshot_unchanged"] = True
        assert not errors, errors
        browser.close()
    report = {"checks": records, "page_errors": errors, "python": sys.executable}
    report["tiny_span_midpoints"] = tiny_midpoints
    (output / "browser-checks.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

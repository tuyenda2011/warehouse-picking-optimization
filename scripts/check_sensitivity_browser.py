"""Check new benchmark charts/CSV in an isolated Edge session."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import expect, sync_playwright
from demo.display import kris_convention
from src.evaluation import load_evaluation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8518")
    args = parser.parse_args()
    content = args.input.read_bytes()
    payload = load_evaluation(content)
    primary = [g for g in payload["groups"] if "sensitivity_design" in g["config"]]
    args.output.mkdir(parents=True, exist_ok=True)
    evidence = {"passed": False, "page_errors": [], "charts": [],
                "input_sha256": hashlib.sha256(content).hexdigest()}
    expect.set_options(timeout=45000)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 768}, accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))

        def settled():
            expect(page.locator('[data-testid="stApp"][data-test-script-state="notRunning"]')).to_be_visible()
            expect(page.get_by_test_id("stSkeleton")).to_have_count(0)
            expect(page.get_by_test_id("stException")).to_have_count(0)
            expect(page.locator('[data-stale="true"]')).to_have_count(0)

        def select(key, label):
            settled()
            page.get_by_test_id("stMain").evaluate("el => el.scrollTo(0, 0)")
            box = page.locator(f".st-key-{key}")
            if box.get_by_role("combobox").input_value() == label:
                return
            box.get_by_role("button", name="Open", exact=True).click()
            page.get_by_role("option", name=label, exact=True).click()
            expect(box.get_by_role("combobox")).to_have_value(label)
            settled()

        def download(label, filename):
            with page.expect_download() as pending:
                page.get_by_role("button", name=label, exact=True).click()
            target = args.output / filename
            pending.value.save_as(target)
            settled()
            return target

        try:
            page.goto(args.url)
            page.get_by_text("Đánh giá benchmark", exact=True).click()
            page.locator('.st-key-evaluation_upload input[type="file"]').set_input_files(str(args.input.resolve()))
            expect(page.get_by_role("tab", name="Tổng hợp", exact=True)).to_be_visible()
            settled()
            page.get_by_role("tab", name="Biểu đồ", exact=True).click()
            expect(page.locator(".st-key-evaluation_figure")).to_be_visible()
            settled()
            labels = {"maps": "Các bản đồ", "kris": "Kris", "scalability": "Quy mô"}
            for group in primary:
                select("evaluation_group", labels.get(group["name"], group["name"]))
                for family in ("Độ nhạy ngân sách thời gian", "Đánh đổi theo trọng số"):
                    box = page.locator(".st-key-evaluation_figure")
                    box.get_by_role("button", name="Open", exact=True).click()
                    option = page.get_by_role("option").filter(has_text=family).first
                    title = option.inner_text()
                    option.click()
                    expect(box.get_by_role("combobox")).to_have_value(title)
                    settled()
                    expect(page.get_by_test_id("stImage")).to_have_count(1)
                    downloaded = download("Tải hình PNG", f"{group['name']}-{len(evidence['charts'])}.png")
                    assert downloaded.read_bytes().startswith(b"\x89PNG")
                    page.get_by_test_id("stMain").evaluate("el => el.scrollTo(0, 0)")
                    page.screenshot(path=str(args.output / f"{group['name']}-{len(evidence['charts'])}-laptop.png"))
                    evidence["charts"].append(title)
                expander = page.get_by_test_id("stExpander").filter(has=page.get_by_text("Dữ liệu độ nhạy và cấu hình", exact=True))
                expander.locator("summary").click()
                convention = kris_convention(group["instances"][0])
                if convention:
                    native_file = download("Tải bảng độ nhạy đơn vị gốc (CSV)", "kris-native.csv")
                    scaled_file = download("Tải bảng độ nhạy theo mô phỏng (CSV)", "kris-simulation.csv")
                    with native_file.open(encoding="utf-8-sig", newline="") as handle:
                        native = list(csv.DictReader(handle))
                    with scaled_file.open(encoding="utf-8-sig", newline="") as handle:
                        scaled = list(csv.DictReader(handle))
                    assert len(native) == len(scaled)
                    for raw, shown in zip(native, scaled, strict=True):
                        assert shown["distance_unit"] == "m" and shown["time_unit"] == "phút"
                        assert raw["objective_mean"] == shown["objective_mean"]
                        assert raw["total_seconds_mean"] == shown["total_seconds_mean"]
                        assert math.isclose(float(shown["distance_mean"]), float(raw["distance_mean"]) * convention["metres_per_source_distance"])
                        assert math.isclose(float(shown["tardiness_mean"]), float(raw["tardiness_mean"]) * convention["seconds_per_source_time"] / 60)
                    evidence["kris_csv_rows"] = len(native)
                expander.locator("summary").click()
            assert not evidence["page_errors"]
            assert args.input.read_bytes() == content
            evidence["passed"] = True
        except Exception as error:
            evidence["error"] = str(error)
            page.screenshot(path=str(args.output / "failure.png"))
            raise
        finally:
            (args.output / "verification.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
            context.close()
            browser.close()
    print(json.dumps(evidence, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()

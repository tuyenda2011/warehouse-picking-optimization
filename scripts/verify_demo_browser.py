"""Verify the local demo in an isolated headless Edge session and retain evidence."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "tmp/upgrade-browser"
FIXTURES = ROOT / "report/generated/upgrade/defense_inputs"


def select(page, label, option):
    expect(page.locator('[data-testid="stApp"][data-test-script-state="notRunning"]')).to_be_visible()
    page.get_by_role("combobox", name=label, exact=True).locator("..").get_by_role("button", name="Open", exact=True).click()
    page.get_by_role("option", name=option, exact=True).click(timeout=10000)
    expect(page.get_by_role("combobox", name=label, exact=True)).to_have_value(option)


def run(url):
    OUTPUT.mkdir(exist_ok=False)
    evidence = {"created_utc": datetime.now(timezone.utc).isoformat(),
                "browser": "system Edge, isolated headless context", "url": url,
                "flows": [], "console_errors": [], "page_errors": []}
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(
            executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
            headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(45000)
        page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
        try:
            response = page.goto(url, wait_until="domcontentloaded")
            assert response and response.ok
            expect(page.get_by_role("heading", name="Tối ưu lấy hàng", exact=True)).to_be_visible()
            page.get_by_role("button", name="Chạy tối ưu", exact=True).click()
            expect(page.get_by_role("tab", name="Mô phỏng", exact=True)).to_be_visible()
            frame = page.frame_locator('iframe[data-testid="stIFrame"]').first
            canvas = frame.locator("#simCanvas")
            expect(canvas).to_be_visible()
            frame.locator("#playBtn").click()
            expect(frame.locator("#playBtn")).to_contain_text("Tiếp tục")
            frame.locator("#resetBtn").click()
            frame.locator("#timelineSlider").evaluate("el => {el.value=40; el.dispatchEvent(new Event('input', {bubbles:true}));}")
            frame.locator('[data-speed="2"]').click()
            frame.locator("#zoomInBtn").click()
            canvas.screenshot(path=str(OUTPUT / "default-canvas.png"))
            assert canvas.evaluate("el => el.width > 100 && el.height > 100")
            page.screenshot(path=str(OUTPUT / "default-page.png"), full_page=True)
            evidence["flows"].append("default optimization; canvas, pause, reset, seek, speed and zoom")

            select(page, "Nguồn dữ liệu", "Tải dữ liệu JSON")
            page.locator('input[type="file"]').set_input_files(str(FIXTURES / "small_exact.json"))
            expect(page.get_by_text("small_exact.json", exact=True)).to_be_visible()
            expect(page.get_by_text(re.compile(r"5 đơn.*sản phẩm")).first).to_be_visible()
            expect(page.locator('[data-testid="stApp"][data-test-script-state="notRunning"]')).to_be_visible()
            advanced = page.locator('[data-testid="stExpander"]').filter(has=page.get_by_text("Nâng cao", exact=True))
            if advanced.get_attribute("open") is None:
                page.get_by_text("Nâng cao", exact=True).click()
            expect(page.get_by_text("Thay đổi các tùy chọn rồi bấm Chạy tối ưu để áp dụng.", exact=True)).to_be_visible()
            page.get_by_text("Có hướng dẫn", exact=True).click()
            expect(page.get_by_role("radio", name="Có hướng dẫn", exact=True)).to_be_checked()
            page.get_by_text("Tăng tốc kiểm tra ứng viên", exact=True).click()
            expect(page.get_by_role("checkbox", name="Tăng tốc kiểm tra ứng viên", exact=True)).to_be_checked()
            page.get_by_role("button", name="Chạy tối ưu", exact=True).click()
            expect(page.get_by_role("tab", name="Mô phỏng", exact=True)).to_be_visible()
            page.get_by_text("Tải kết quả", exact=True).click()
            with page.expect_download() as pending:
                page.get_by_role("button", name="Tải toàn bộ lần chạy (JSON)", exact=True).click()
            download = pending.value
            target = OUTPUT / "guided-snapshot.json"
            download.save_as(str(target))
            snapshot = json.loads(target.read_text(encoding="utf-8"))
            config = snapshot["results"]["ALNS"]["search"]["config"]
            assert config["candidate_policy"] == "guided" and config["incremental_validation"] is True
            assert len(snapshot["instance"]["orders"]) == 5
            page.screenshot(path=str(OUTPUT / "guided-page.png"), full_page=True)
            evidence["flows"].append("upload certified tiny input; guided/incremental flags reach exported ALNS config")

            page.locator('input[type="file"]').set_input_files(str(FIXTURES / "invalid_capacity.json"))
            page.get_by_role("button", name="Chạy tối ưu", exact=True).click()
            expect(page.get_by_text("Không thể chạy thuật toán. Hãy kiểm tra dữ liệu và thông số đã chọn.", exact=True)).to_be_visible()
            expect(page.get_by_role("tab", name="Mô phỏng", exact=True)).to_have_count(0)
            page.screenshot(path=str(OUTPUT / "invalid-page.png"), full_page=True)
            evidence["flows"].append("invalid capacity is rejected and previous result is cleared")
            assert not evidence["page_errors"], evidence["page_errors"]
            evidence["passed"] = True
        except Exception as error:
            evidence["passed"] = False
            evidence["error"] = str(error)
            evidence["comboboxes"] = page.get_by_role("combobox").evaluate_all("els => els.map(el => ({label:el.getAttribute('aria-label'), text:el.innerText}))")
            evidence["options"] = page.get_by_role("option").all_text_contents()
            page.screenshot(path=str(OUTPUT / "failure-page.png"), full_page=True)
            raise
        finally:
            context.close()
            browser.close()
            evidence["artifacts_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                           for p in sorted(OUTPUT.iterdir()) if p.is_file()}
            (OUTPUT / "verification.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    run(parser.parse_args().url)

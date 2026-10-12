"""Portable, independently audited evaluation reports with optional figures."""
from __future__ import annotations

import csv
from html import escape
import json
from pathlib import Path
from typing import Any

from .models import InputError


def _write_csv(path: Path, rows: list[dict], fallback: list[str]) -> None:
    columns = list(dict.fromkeys(key for row in rows for key in row)) or fallback
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _report(payload: dict, summary: list[dict], availability: dict) -> str:
    lines = ["# Kết quả đánh giá benchmark", "", f"Chế độ: **{_cell(payload['preset'])}**. "
             f"Thời điểm tạo kết quả: {_cell(payload['created_at_utc'])}.", "",
             "Mở **[index.html](index.html)** bằng trình duyệt để xem trước và chọn từng hình PNG.", "",
             "- Hình cho báo cáo: `figures_report/`, chia thư mục theo nhóm dữ liệu.",
             "- Hình cho slide: `figures_presentation/` nếu bật `--presentation`; khung 16:9, chữ lớn.",
             "- Mỗi PNG chứa một biểu đồ. Số liệu và màu thuật toán thống nhất giữa hai bản.",
             "- Nạp `evaluation.json` vào mục **Đánh giá benchmark** trong demo để xem bảng và biểu đồ.", ""]
    if payload["preset"] == "quick":
        lines += ["**QUICK — chỉ là bằng chứng pipeline/demo. Số instance, seed và ngân sách nhỏ không đủ cho kết luận khoa học tổng quát.**", ""]
    lines += ["Các phương án trong evaluation.json đã được kiểm định trước khi xuất. Việc xuất bảng và hình không chạy lại thuật toán.", "",
              "## Dữ liệu đã chạy", "", "| Nhóm | Bài toán | Lần chạy | Số đơn | Thuật toán | Seed tìm kiếm |",
              "|---|---:|---:|---|---|---|"]
    for group in payload["groups"]:
        results = group["results"]
        lines.append("| " + " | ".join(_cell(value) for value in [group["name"], len(group["instances"]), len(results),
                     ", ".join(map(str, sorted({len(i["orders"]) for i in group["instances"]}))),
                     ", ".join(sorted({r["method"] for r in results})),
                     ", ".join(map(str, sorted({r["search"]["seed"] for r in results})))]) + " |")
    skipped = payload["provenance"].get("skipped_groups", {})
    if isinstance(skipped, dict) and skipped:
        lines += ["", "Nhóm không chạy:", ""]
        lines += [f"- {_cell(name)}: {_cell(reason)}" for name, reason in skipped.items()]
    lines += ["", "## So sánh cặp theo instance", "",
              "Lấy trung bình search seed trong từng instance trước. Mỗi instance có một phiếu; F thấp hơn là tốt hơn. "
              "Bảng summary.csv lưu cả tham chiếu B0 và B2. Tỷ lệ chỉ dùng cặp có mẫu số tham chiếu khác 0.", "",
              "| Nhóm | Method | Tham chiếu | Instance | Thắng | Hòa | Thua | Cải thiện F trung bình (%) |",
              "|---|---|---|---:|---:|---:|---:|---:|"]
    for row in summary:
        improvement = row.get("mean_improvement_pct")
        cells = [row["group"], row["method"], row["reference"], row["instances"], row["win"], row["tie"], row["loss"],
                 "N/A" if improvement is None else f"{improvement:.4f}"]
        lines.append("| " + " | ".join(_cell(value) for value in cells) + " |")
    lines += ["", "## Danh mục hình", "",
              "Chỉ xuất PNG 300 dpi. Mỗi nhóm dùng B2 làm đối chứng nếu có, nếu thiếu B2 thì dùng B0. "
              "Bản slide là ảnh để chèn vào bài thuyết trình, không phải tệp PowerPoint.", ""]
    for style, label in (("report", "Báo cáo"), ("presentation", "Slide")):
        if not availability[style]:
            continue
        lines += [f"### {label}", "", "| Nhóm | Biểu đồ | PNG hoặc lý do không xuất |", "|---|---|---|"]
        for entry in availability[style]:
            link = f"[Mở hình]({entry['files']['png']})" if entry["available"] else _cell(entry["reason"])
            lines.append(f"| {_cell(entry['group'])} | {_cell(entry['title'])} | {link} |")
    lines += ["## Giới hạn diễn giải", "",
              "- Không gộp giá trị có đơn vị vật lý giữa các nhóm; các tỷ lệ được tính trên cặp cùng instance.",
              "- Độ lệch chuẩn/min–max và hộp seed mô tả độ phân tán; không phải khoảng tin cậy hoặc kiểm định ý nghĩa thống kê.",
              "- Instance seed được dùng lại ở các quy mô có tương quan; seed tìm kiếm không phải instance độc lập.",
              "- Các ví dụ ổn định/hội tụ chọn cố định tối đa ba instance theo số đơn rồi tên, trước khi xem kết quả; không chọn ca đẹp nhất.",
              "- Hội tụ chỉ vẽ giao khoảng thời gian đã ghi của mọi seed/method trên cùng instance. Không suy diễn trước khởi tạo hoặc bổ sung mốc cuối chưa quan sát.",
              "- Ca không có search hoặc chỉ một search seed vẫn được giữ trong bảng điểm; không đủ để khẳng định lợi ích hoặc độ ổn định của search.",
              "- Scalability yêu cầu nhiều quy mô và layout/operations có kiểm soát; các bản đồ demo khác layout hoặc số picker là các kịch bản riêng.",
              "- Kết quả chỉ áp dụng cho dữ liệu, cấu hình, máy và seed đã lưu; không chứng minh một method luôn tốt hơn.", "",
              "## Tệp dữ liệu", "", "- summary.csv: so sánh B0/B2 trên cặp instance.",
              "- per_instance.csv: một hàng cho mỗi instance/method; thống kê seed một lần, tỷ lệ và chênh lệch có hậu tố _vs_B0 / _vs_B2.",
              "- raw_metrics.csv: một hàng cho mỗi lần chạy đã xác thực.",
              "- evaluation.json: dữ liệu, phương án, cấu hình đầy đủ và thông tin truy xuất nguồn; có thể chuyển máy và nạp vào demo.",
              "- availability.json: đường dẫn, cách tính từng hình và lý do không xuất.", ""]
    if any("sensitivity_design" in g["config"] for g in payload["groups"]):
        lines += ["## Khảo sát độ nhạy bổ sung", "",
                  "[sensitivity.csv](sensitivity.csv) chứa ngân sách yêu cầu, thời gian thực đo, profile trọng số, "
                  "trung bình/SD và số lượt 0 vòng của từng input/method/điều kiện. "
                  "Các điều kiện dùng cùng input và seed, được khóa trước khi giải và chạy tuần tự theo thứ tự xáo cố định. "
                  "Khảo sát thăm dò trên tối đa ba input mỗi nhóm; không coi seed là input độc lập. "
                  "Hình 06: F theo ngân sách với trọng số cân bằng. Hình 07: quãng đường–độ trễ, "
                  "không so F giữa trọng số hoặc khẳng định Pareto tối ưu. Râu là SD, không phải CI.", ""]
    return "\n".join(lines)


def _gallery(payload: dict, availability: dict) -> str:
    """A local image catalogue; full method notes are collapsed by default."""
    primary = [g for g in payload["groups"] if "sensitivity_condition" not in g["config"]]
    cases = sum(len(g["instances"]) for g in payload["groups"] if "sensitivity_condition" in g["config"])
    lines = ["<!doctype html><html lang='vi'><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width, initial-scale=1'>",
             "<title>Hình đánh giá benchmark</title><style>",
             "body{font:16px/1.5 system-ui,sans-serif;background:#f5f7fa;color:#172538;max-width:1200px;margin:32px auto;padding:0 20px}",
             "h1,h2{line-height:1.2}a{color:#195b9c}nav{display:flex;gap:20px;flex-wrap:wrap;margin:20px 0}",
             ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:18px}",
             "article{background:white;border:1px solid #d9e0e8;border-radius:8px;padding:16px;overflow-wrap:anywhere}",
             "article img{width:100%;height:220px;object-fit:contain}h3{font-size:17px;margin:10px 0}details{margin-top:12px}summary{cursor:pointer}",
             ".missing{background:#fff8e9;padding:12px;border-radius:4px}.meta{color:#516074}</style>",
             "<h1>Hình đánh giá benchmark</h1>",
             f"<p class='meta'>{len(primary)} nhóm dữ liệu · "
             f"{sum(len(g['instances']) for g in primary)} bài toán chính · "
             + (f"{cases} ca đầu vào–điều kiện bổ sung · " if cases else "") +
             f"{sum(len(g['results']) for g in payload['groups'])} lượt chạy · Chế độ {escape(payload['preset'])}</p>",
             "<p>Mỗi ảnh PNG chứa một biểu đồ. Bấm <strong>Mở PNG</strong> để xem ảnh đầy đủ và lưu vào báo cáo hoặc slide. "
             "Bảng và ảnh dùng cùng kết quả đã kiểm định.</p>",
             "<nav><a href='summary.csv'>Bảng tổng CSV</a><a href='per_instance.csv'>Bảng từng bài toán CSV</a>"
             "<a href='evaluation.json' download>evaluation.json cho demo</a><a href='REPORT.md'>Hướng dẫn</a></nav>"]
    for style, label in (("report", "Hình cho báo cáo"), ("presentation", "Hình cho slide — 16:9")):
        entries = availability[style]
        if not entries:
            continue
        lines.append(f"<h2>{label}</h2>")
        for group in payload["groups"]:
            selected = [entry for entry in entries if entry["group"] == group["name"]]
            if not selected:
                continue
            lines += [f"<h3>{escape(group['name'])} · Đối chứng {escape(availability['references'][group['name']])}</h3>",
                      "<div class='grid'>"]
            for entry in selected:
                title = escape(entry["title"])
                lines += ["<article>", f"<h3>{title}</h3>"]
                if entry["available"]:
                    path = escape(entry["files"]["png"], quote=True)
                    lines += [f"<a href='{path}'><img loading='lazy' src='{path}' alt='{title}'></a>",
                              f"<a href='{path}'>Mở PNG</a> · <a href='{path}' download>Tải PNG</a>",
                              f"<details><summary>Cách đọc và cách tính</summary><p>{escape(entry['caption'])}</p></details>"]
                else:
                    lines.append(f"<p class='missing'>Không xuất: {escape(entry['reason'] or 'Chưa đủ dữ liệu.')}</p>")
                lines.append("</article>")
            lines.append("</div>")
    if any("sensitivity_design" in g["config"] for g in payload["groups"]):
        lines.append("<p><a href='sensitivity.csv' download>Dữ liệu độ nhạy CSV</a>: "
                     "ngân sách yêu cầu, thời gian thực đo, profile và số lượt 0 vòng. "
                     "Râu là SD, không phải CI; không so F giữa trọng số hoặc khẳng định Pareto tối ưu.</p>")
    lines.append("</html>")
    return "\n".join(lines)


def _figure_filename(spec: dict) -> str:
    family, _, suffix = spec["id"].rsplit("__", 1)[1].partition("_")
    stems = {"quality": "01_chat_luong", "components": "02_thanh_phan",
             "stability": "03_on_dinh", "convergence": "04_hoi_tu", "scalability": "05_quy_mo",
             "budget": "06_do_nhay_ngan_sach", "weights": "07_danh_doi_trong_so"}
    if family == "components":
        return {"distance": "02_quang_duong.png", "makespan": "02_thoi_gian_hoan_tat.png",
                "tardiness": "02_tong_do_tre.png"}[suffix]
    if suffix.startswith("example"):
        suffix = f"vi_du_{int(suffix.removeprefix('example')):02d}"
    elif suffix.startswith("p") and suffix[1:].isdigit():
        suffix = f"trang_{int(suffix[1:]):02d}"
    else:
        suffix = {"runtime": "thoi_gian", "quality": "chat_luong"}.get(suffix, suffix)
    return stems[family] + (f"_{suffix}" if suffix else "") + ".png"


def export_evaluation(payload: dict, output: str | Path, presentation: bool = False,
                      charts: bool = True) -> dict[str, Any]:
    """Validate first, then export into a new or empty directory without overwrite."""
    from .evaluation import evaluation_tables, validate_evaluation

    validate_evaluation(payload)
    output = Path(output)
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise InputError("Evaluation export requires a new or empty directory; refusing to overwrite evidence")
    tables = {reference: evaluation_tables(payload, reference=reference) for reference in ("B0", "B2")}
    summary = [dict(row, reference=reference) for reference, table in tables.items() for row in table["summary"]]
    per_instance_by_key = {}
    for reference, table in tables.items():
        for row in table["per_instance"]:
            key = (row["group"], row["instance"], row["method"])
            merged = per_instance_by_key.setdefault(key, {
                field: value for field, value in row.items()
                if field != "reference" and not field.endswith(("_improvement_pct", "_difference"))})
            merged.update({f"{field}_vs_{reference}": value for field, value in row.items()
                           if field.endswith(("_improvement_pct", "_difference"))})
    per_instance = list(per_instance_by_key.values())
    raw = tables["B2"]["raw_metrics"]
    from .sensitivity import condition_rows
    sensitivity = condition_rows(payload, tables["B2"])
    # Serialize before creating a directory so malformed non-JSON provenance
    # cannot leave a partial export beside otherwise valid solver evidence.
    portable = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    references = {group["name"]: ("B2" if any(result["method"] == "B2" for result in group["results"]) else "B0")
                  for group in payload["groups"]}
    output.mkdir(parents=True, exist_ok=True)
    _write_csv(output / "summary.csv", summary, ["group", "method", "reference"])
    _write_csv(output / "per_instance.csv", per_instance, ["group", "instance", "method"])
    _write_csv(output / "raw_metrics.csv", raw, ["group", "instance", "method", "search_seed"])
    if sensitivity:
        _write_csv(output / "sensitivity.csv", sensitivity,
                   ["parent_group", "instance", "method", "profile", "budget_seconds"])
    (output / "evaluation.json").write_text(portable, encoding="utf-8")
    common_reference = next(iter(set(references.values()))) if len(set(references.values())) == 1 else None
    availability = {"schema_version": 1, "reference": common_reference, "references": references, "charts_requested": charts,
                    "report": [], "presentation": []}
    from .evaluation_figures import _figure_specs_from_tables, _slug, _spec, families_for, figure_bytes
    # Reuse the audited tables across groups and styles. Render one group at a
    # time rather than keeping the complete report's figures in memory.
    for index, group in enumerate(payload["groups"], 1):
        if "sensitivity_condition" in group["config"]:
            continue
        reference = references[group["name"]]
        directory = f"{index:02d}_{_slug(group['name'])}"
        for style in ("report", "presentation") if presentation else ("report",):
            specs = (_figure_specs_from_tables(payload, tables[reference], reference, group["name"], style)
                     if charts else [_spec(group, family, reason="Biểu đồ bị tắt; dùng các bảng CSV.")
                                     for family in families_for(group)])
            try:
                for spec in specs:
                    entry = {key: spec[key] for key in ("id", "title", "caption", "reason", "group")}
                    entry.update(reference=reference, available=spec["figure"] is not None, files={})
                    if spec["figure"] is not None:
                        relative = f"figures_{style}/{directory}/{_figure_filename(spec)}"
                        target = output / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(figure_bytes(spec["figure"]))
                        entry["files"]["png"] = relative
                        spec["figure"].clear()
                    availability[style].append(entry)
            finally:
                for spec in specs:
                    if spec["figure"] is not None:
                        spec["figure"].clear()
    _json(output / "availability.json", availability)
    (output / "REPORT.md").write_text(_report(payload, summary, availability), encoding="utf-8")
    (output / "index.html").write_text(_gallery(payload, availability), encoding="utf-8")
    return {"output": str(output), "groups": len(payload["groups"]), "instances": sum(len(g["instances"]) for g in payload["groups"]),
            "raw_runs": len(raw), "summary_rows": len(summary), "availability": availability}

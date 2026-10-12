"""Vietnamese presentation text for shared evaluation figures; calculations stay in src."""
import re

TITLES = {
    "Chất lượng nghiệm": "Chất lượng phương án",
    "Các thành phần mục tiêu": "Các thành phần của mục tiêu",
    "Độ ổn định giữa các seed": "Độ ổn định giữa các lần chạy",
    "Hội tụ theo thời gian thực": "Quá trình cải thiện theo thời gian",
    "Thay đổi theo quy mô đơn hàng": "Ảnh hưởng của quy mô đơn hàng",
}


def display_text(value):
    for original, translated in TITLES.items():
        value = value.replace(original, translated)
    value = re.sub(r"\bInstance\b", "Bài toán", value)
    value = re.sub(r"\binstance\b", "bài toán", value)
    value = re.sub(r"\b(\d+) seed\b", r"\1 lần chạy", value)
    for original, translated in (
        ("Tổng trễ hạn", "Tổng độ trễ"), ("dương = tốt hơn", "số dương là tốt hơn"),
        (" · thấp hơn = tốt hơn", ""), (" · thấp hơn là tốt hơn", ""),
        (" · số dương là tốt hơn", ""),
        ("Thời gian tối ưu gồm khởi tạo", "Thời gian tối ưu, kể cả khởi tạo"),
        (" · heuristic", ""),
    ):
        value = value.replace(original, translated)
    return value


def short_caption(family, reference, current, suffix=""):
    components = {"distance": "quãng đường", "makespan": "thời gian hoàn tất", "tardiness": "tổng độ trễ"}
    if family == "components" and suffix in components:
        return (f"Mức cải thiện {components[suffix]} so với {reference}, sau khi lấy trung bình các lần chạy trên từng bài toán. "
                "Chấm mờ là từng bài toán; ký hiệu đậm là trung bình; thanh ngang trải từ nhỏ nhất đến lớn nhất, không phải khoảng tin cậy. "
                "n là số bài toán có giá trị đối chứng khác 0.")
    if family == "scalability" and suffix == "runtime":
        return ("Thời gian chạy trung bình theo số đơn, khi giữ nguyên bố trí kho, sản phẩm và cách tổ chức nhân viên. "
                "Các lần chạy được lấy trung bình trên từng bài toán trước; râu trải từ nhỏ nhất đến lớn nhất giữa các bài toán cùng quy mô, không phải khoảng tin cậy.")
    if family == "scalability" and suffix == "quality":
        return (f"Mức cải thiện F so với {reference} theo số đơn, khi giữ nguyên điều kiện kho và cách tổ chức nhân viên. "
                "So sánh trên cùng bài toán sau khi lấy trung bình các lần chạy; số dương là tốt hơn. "
                "Râu trải từ nhỏ nhất đến lớn nhất giữa các bài toán cùng quy mô, không phải khoảng tin cậy.")
    captions = {
        "budget": "Cùng đầu vào và seed, thay ngân sách yêu cầu. Điểm là F trung bình; râu là SD giữa seed, không phải CI. Ngân sách khác thời gian thực đo; giữ cả ca 0 vòng và kết quả bất lợi.",
        "weights": "Cùng đầu vào, seed và ngân sách, thay profile trọng số. So quãng đường và tổng độ trễ; không so F giữa trọng số. Điểm là trung bình, râu là SD giữa seed; các điểm trùng có thể chồng nhau. Đây không phải biên Pareto tối ưu.",
        "quality": f"Mỗi điểm là mức cải thiện F so với {reference} trên cùng bài toán, sau khi lấy trung bình các lần chạy. Mỗi bài toán có trọng số như nhau; số dương là tốt hơn. Không tính tỷ lệ khi F đối chứng bằng 0.",
        "components": f"So sánh quãng đường, thời gian hoàn tất và tổng độ trễ với {reference}. Chấm mờ là từng bài toán; ký hiệu đậm là trung bình; thanh ngang trải từ giá trị nhỏ nhất đến lớn nhất, không phải khoảng tin cậy. n là số bài toán tính được tỷ lệ cho từng chỉ số.",
        "stability": "Mỗi chấm là một lần chạy với seed khác nhau. Hộp thể hiện khoảng Q1–Q3 và trung vị; râu theo quy tắc 1,5 IQR. Biểu đồ mô tả mức dao động giữa các lần chạy, không phải khoảng tin cậy.",
        "convergence": ("Với một seed, đường bậc thang là F tốt nhất đạt được đến từng thời điểm; chưa thể đánh giá độ ổn định. " if current else
                        "Đường bậc thang là F tốt nhất đến từng thời điểm, lấy trung bình qua các lần chạy; vùng mờ trải từ nhỏ nhất đến lớn nhất, không phải khoảng tin cậy. ") +
                       "Chỉ vẽ khoảng thời gian mà các lần chạy đều có dữ liệu. Đường ngang là giá trị F cuối cùng của các thuật toán cơ sở, dùng để đối chiếu.",
        "scalability": "Giữ nguyên bố trí kho, danh mục sản phẩm, đơn vị và cách tổ chức nhân viên khi thay đổi số đơn. Các lần chạy được lấy trung bình trên từng bài toán trước; mỗi điểm là trung bình các bài toán cùng quy mô. Râu trải từ nhỏ nhất đến lớn nhất, không phải khoảng tin cậy.",
    }
    return captions.get(family, "")


def unavailable_text(reason, family, reference, current):
    if "Matplotlib" in reason:
        return "Chưa có thư viện Matplotlib để vẽ biểu đồ. Bạn vẫn có thể xem và tải bảng CSV."
    if family == "quality":
        return f"Chưa có bài toán đủ dữ liệu để so sánh với đối chứng {reference}. Khi F đối chứng bằng 0, không tính được tỷ lệ cải thiện."
    if family == "components":
        return f"Chưa đủ dữ liệu để so sánh các chỉ số với {reference}. Chỉ số có giá trị đối chứng bằng 0 không tính được tỷ lệ cải thiện."
    if family == "stability":
        return "Để so sánh độ ổn định, cần ít nhất 2 seed khác nhau cho một thuật toán tìm kiếm trên cùng bài toán được chọn."
    if family == "convergence":
        return ("Lịch sử tìm kiếm của lần chạy hiện tại cần có ít nhất 2 mốc thời gian khác nhau. Chỉ vẽ trong khoảng đã ghi nhận." if current else
                "Để vẽ quá trình cải thiện, cần ít nhất 2 seed có lịch sử tìm kiếm hợp lệ và một khoảng thời gian chung được ghi nhận.")
    if family == "scalability":
        if reason.startswith("Cần ít nhất 2"):
            return reason
        if reason.startswith("Layout"):
            return "Bố trí kho, danh mục sản phẩm, đơn vị hoặc cách tổ chức nhân viên khác nhau. Nhóm này phù hợp để so sánh kịch bản, chưa đủ để đánh giá riêng ảnh hưởng của quy mô."
        return "Nhóm này chưa được thiết lập để đánh giá theo quy mô, và chưa có đủ thông tin để xác nhận bố trí kho được giữ cố định."
    return display_text(reason)


def localize_spec(spec, reference):
    """Change text on a newly created demo figure without touching data or source files."""
    localized = dict(spec)
    family_id = spec["id"].rsplit("__", 1)[1].split("_", 1)
    family, suffix = family_id[0], family_id[1] if len(family_id) > 1 else ""
    current = spec.get("group") == "current_run"
    localized["title"] = display_text(spec["title"])
    localized["technical_caption"] = spec.get("caption") or spec.get("reason")
    localized["caption"] = short_caption(family, reference, current, suffix) if spec.get("caption") else ""
    if spec.get("reason"):
        localized["reason"] = unavailable_text(spec["reason"], family, reference, current)
    figure = spec.get("figure")
    if figure is not None:
        for text in figure.texts:
            text.set_text(display_text(text.get_text()))
        for axis in figure.axes:
            axis.set(title=display_text(axis.get_title()), xlabel=display_text(axis.get_xlabel()),
                     ylabel=display_text(axis.get_ylabel()))
            labels = [text.get_text() for text in axis.get_xticklabels()]
            translated = [display_text(label) for label in labels]
            if labels != translated:
                axis.set_xticks(axis.get_xticks(), translated)
            legend = axis.get_legend()
            if legend is not None:
                for text in legend.get_texts():
                    text.set_text(display_text(text.get_text()))
    return localized

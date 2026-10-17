# 📦 Warehouse Joint Optimizer

**Tối ưu gom đơn, định tuyến và lập lịch lấy hàng cho nhiều nhân viên.**

[🇻🇳 Tiếng Việt](README.md) · [🇬🇧 English](README.en.md)

Bài tập lớn **Thuật toán ứng dụng**, gồm bộ giải Python, giao diện mô phỏng Streamlit và benchmark cho năm phương pháp **B0, B2, LNS, ALNS, VNS**.

## 🎬 Xem các kho hoạt động

### 🏭 Kho chuẩn

5 dãy × 6 hàng, 30 SKU, 10 đơn, 3 nhân viên, sức chứa 20.

![Kho chuẩn](assets/readme/single_block.gif)

### 🏗️ Kho 2 khối

6 dãy × 8 hàng, 48 SKU, một lối ngang bên trong, 30 đơn, 3 nhân viên, sức chứa 25.

![Kho 2 khối](assets/readme/double_block.gif)

### 🏢 Kho lớn

10 dãy × 16 hàng, 160 SKU, hai lối ngang bên trong, 40 đơn, 5 nhân viên, sức chứa 30.

![Kho lớn](assets/readme/mega_hub.gif)

### ⚡ Cao điểm

Cùng bố trí kho 2 khối, 25 đơn, 4 nhân viên, sức chứa 20, hệ số nới hạn giao 0,06.

![Cao điểm](assets/readme/rush_hour.gif)

### 🎯 Phân khu ABC

6 dãy × 10 hàng, 60 SKU, 35 đơn, 4 nhân viên, sức chứa 25. Nhóm 20% SKU gần depot nhất nhận 70% trọng số lấy mẫu nhu cầu; đây không phải tỷ lệ quan sát thực tế.

![Phân khu ABC](assets/readme/abc_zonal.gif)

### 🗺️ Kris Small

Đầu vào `instances_100_1`: 18 đơn, 35 SKU, 72 đỉnh và 2 nhân viên. GIF giữ tọa độ nguồn; đồng hồ đổi sang phút theo quy ước hiển thị của dự án (thời gian nguồn chia 1.800). Các đường nối là cạnh đồ thị, không phải sơ đồ kệ được suy diễn.

![Mô phỏng Kris Small](assets/readme/kris_small.gif)

Các GIF hiển thị mã nhân viên ngay trên vị trí, vệt di chuyển gần đây, trạng thái chuẩn bị/di chuyển/lấy hàng, thanh tải theo sức chứa, số đơn hoàn thành và tiến trình phát. Vòng sáng đánh dấu nhân viên đang lấy hàng; các nhân viên có thể trùng vị trí tại depot theo mô hình không xét va chạm.

## 🚀 Cài đặt

Yêu cầu **Python 3.10 trở lên**. Chạy tại thư mục gốc:

```console
python -m venv .venv
```

Windows:

```console
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run demo/app.py
```

Linux/macOS:

```console
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run demo/app.py
```

Nếu có Conda `TTUD`, chạy `conda activate TTUD`, cài requirements rồi mở Streamlit. Demo mặc định tại [localhost:8501](http://localhost:8501). Các lệnh sau dùng Python của môi trường đã cài; Windows có thể thay `python` bằng `.\.venv\Scripts\python.exe`.

## 🖥️ Sử dụng demo

1. Chọn **Mô phỏng** trên thanh bên.
2. Chọn dữ liệu mô phỏng, Kris hoặc tải JSON.
3. Chọn bản đồ, số đơn, nhân viên và sức chứa.
4. Bật **So sánh 5 thuật toán** nếu cần; mặc định chạy B0 và ALNS.
5. Bấm **Chạy tối ưu** và xem các tab kết quả.

| Tab | Nội dung |
|---|---|
| Mô phỏng | Phát lại, đổi tốc độ, tua và chọn nhân viên. |
| Tổng quan | Quãng đường, makespan, đơn trễ và F. |
| Tuyến và lịch | Tuyến từng chuyến và lịch nhân viên. |
| Chi tiết | Chuyến, đơn và hàng hóa. |
| Đánh giá | So sánh trong lần chạy hiện tại. |

Trong **Nâng cao**, có thể đổi seed, ngân sách, trọng số, lựa chọn ứng viên guided và kiểm tra ứng viên tăng tốc. Chạy lại sau khi đổi đầu vào; chuyển tab không chạy lại thuật toán.

Để xem nhiều bài và seed, chọn **Đánh giá benchmark**, mở `evaluation.json`, chọn nhóm dữ liệu và thuật toán đối chứng. Có thể tải CSV và PNG. Gói đánh giá chứa đầu vào và nghiệm để kiểm tra trên máy khác.

## 🧠 Mô hình và thuật toán

Mỗi đơn thuộc đúng một chuyến, tải chuyến không vượt sức chứa. Chuyến bắt đầu và kết thúc tại depot, đi theo đồ thị kho. Nhân viên thực hiện chuyến lần lượt; đơn hoàn thành khi chuyến trở về depot.

| Phương pháp | Cơ chế |
|---|---|
| B0 | Gom theo thứ tự, tuyến nearest neighbor, lập lịch theo quy tắc cố định. |
| B2 | Gom tham lam, cải thiện tuyến bằng 2-opt. |
| LNS | Phá hủy một phần nghiệm và tái thiết. |
| ALNS | Điều chỉnh xác suất chọn toán tử theo hiệu quả tìm kiếm. |
| VNS | Thay đổi lân cận của đơn, chuyến và lịch. |

**F** kết hợp quãng đường, makespan và tổng độ trễ sau chuẩn hóa theo B0. **F thấp hơn tốt hơn trên cùng đầu vào và trọng số.** Hạn giao mềm; giảm tổng độ trễ chưa bảo đảm giảm số đơn trễ. Mô hình giả định đơn có sẵn từ thời điểm 0, nhân viên đồng nhất, chưa xét va chạm và ca nghỉ.

Kris giữ đơn vị nguồn trong bộ giải. Giao diện quy đổi 10 đơn vị khoảng cách nguồn thành 1 m, với thời gian tương ứng vận tốc 60 m/phút. Đây là quy ước hiển thị chưa hiệu chuẩn thực tế; JSON giữ dữ liệu gốc.

## ⌨️ Dòng lệnh

```console
python -m src generate --scenario double_block --orders 20 --pickers 4 --capacity 30 --seed 42 --output data/synthetic/example.json
python -m src solve data/synthetic/example.json --method ALNS --seconds 3 --iterations 100000 --seed 42 --output results/example/solution.json
python -m src validate data/synthetic/example.json results/example/solution.json
```

Dùng `--profile balanced`, `distance`, `makespan`, `tardiness` hoặc `--weights` với ba trọng số dương có tổng bằng 1. Biến thể `--candidate-policy guided --incremental-validation` không bảo đảm tốt hơn trên mọi bài.

Để tái lập theo số vòng, dùng `--seconds 0 --iterations 200` cùng đầu vào, seed và cấu hình. Ngân sách giây chịu ảnh hưởng tải máy. Bộ giải `exact` giới hạn 6 đơn và 8 vị trí hàng ngoài depot; chỉ chứng nhận tối ưu khi `certified_optimal=true`.

```console
python -m src --help
python -m src solve --help
python -m src exact --help
```

## 📊 Benchmark

Cấu hình: [configs/benchmark.json](configs/benchmark.json).

| Nhóm | Phạm vi |
|---|---|
| `maps` | Năm kịch bản kho mô phỏng. |
| `scalability` | Tăng số đơn trên cấu hình kho cố định. |
| `kris` | 18 bài Kris Small với 6, 12 và 18 đơn. |

Kiểm tra cấu hình, chạy thử và chạy đầy đủ:

```console
python -m src benchmark --config configs/benchmark.json --preset report --groups maps scalability kris --dry-run
python -m src benchmark --config configs/benchmark.json --preset quick --groups maps scalability --output results/benchmark_quick_01 --presentation
python -m src benchmark --config configs/benchmark.json --preset report --groups maps scalability kris --output results/benchmark_report_02 --presentation
```

Preset report hiện có 45 bài chính, 1.440 lượt chính và 765 lượt khảo sát ngân sách/trọng số, tổng 2.205 lượt. B0/B2 chạy một lần mỗi bài; LNS/ALNS/VNS dùng 10 seed, ngân sách khởi tạo và tìm kiếm 3 giây mỗi lượt chính. Các khảo sát bổ sung trong báo cáo chạy riêng; lệnh trên không tự sinh toàn bộ 2.475 kết quả của báo cáo.

Kris cần catalog và JSON đã chuyển đổi, xem [hướng dẫn dữ liệu](data/README.md). Nếu thiếu, chọn `--groups maps scalability`. Mỗi đợt dùng thư mục mới hoặc rỗng. Thêm `--resume` để dùng lại nhóm hoàn thành và qua kiểm tra; nhóm dở chạy lại từ đầu.

Xuất lại hình và bảng từ kết quả đã lưu, không chạy lại tìm kiếm:

```console
python -m src report --input results/benchmark_report_02 --output results/benchmark_png_02/report --presentation
```

| Đầu ra trong `report/` của đợt benchmark | Công dụng |
|---|---|
| `index.html`, `REPORT.md` | Danh mục hình và cách đọc kết quả. |
| `summary.csv`, `per_instance.csv` | Tổng hợp nhóm và từng bài. |
| `raw_metrics.csv`, `sensitivity.csv` | Chỉ tiêu từng lượt và khảo sát. |
| `figures_report/`, `figures_presentation/` | PNG cho báo cáo và slide, không tạo PowerPoint. |
| `evaluation.json` | Gói mở trên demo. |

Lấy trung bình seed trong từng bài trước khi tổng hợp nhóm. Độ lệch chuẩn không phải khoảng tin cậy. Nhóm maps đổi nhiều yếu tố đồng thời; dùng scalability để khảo sát số đơn. Không xếp hạng trực tiếp F khác trọng số.

## 📚 Cấu trúc và tài liệu

```text
demo/             Giao diện và mô phỏng động
src/              Mô hình, bộ giải, kiểm định, benchmark và xuất kết quả
configs/          Cấu hình thực nghiệm
data/             Dữ liệu nguồn, mô phỏng và chuyển đổi
assets/readme/    GIF và thông tin cấu hình
scripts/          Công cụ hỗ trợ
tests/            Kiểm thử
report/           Báo cáo LaTeX và PDF
results/          Kết quả sinh khi chạy, Git bỏ qua
```

- [Nguồn và chuẩn bị dữ liệu](data/README.md)
- [Báo cáo PDF](report/main.pdf)
- [Mã nguồn báo cáo](report/main.tex)

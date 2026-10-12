# Warehouse Joint Optimizer — Tối ưu lấy hàng trong kho

Đồ án môn **Thuật toán ứng dụng**, giải bài toán kết hợp **gom đơn hàng thành chuyến, tìm đường lấy hàng và phân công chuyến cho nhiều nhân viên**.

Dự án có bộ giải Python, giao diện mô phỏng Streamlit và benchmark dùng chung cho phần đánh giá trên demo, slide thuyết trình và báo cáo. Kết quả benchmark được lưu để xuất lại bảng, hình hoặc mở trên máy khác.

Đợt cải tiến có đối chứng riêng tại `results/high_score_upgrade_20261010`:
456 lượt phát triển, chọn cấu hình trước 36 bài holdout mới. Nguồn cũ và nguồn
mới được lưu riêng; benchmark lịch sử không bị ghi đè. Xem
[nhật ký nghiên cứu](docs/UPGRADE_RESEARCH_LOG.md) và [hướng dẫn báo cáo](report/README.md).
Lựa chọn guided là opt-in; mặc định uniform giữ hành vi cũ.

**Python từ 3.10** · **Streamlit** · **B0, B2, LNS, ALNS, VNS**

## 1. Cài đặt và mở demo

Mở terminal tại thư mục gốc của dự án, nơi có `README.md` và `pyproject.toml`, rồi chạy các lệnh bên dưới.

### Dùng môi trường Conda TTUD có sẵn

```console
conda activate TTUD
python -m pip install -r requirements.txt
python -m streamlit run demo/app.py
```

### Tạo môi trường mới trên Windows

```console
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run demo/app.py
```

Nếu dùng môi trường `.venv`, thay `python` trong các lệnh bên dưới bằng `.\.venv\Scripts\python.exe`.

Trên Linux/macOS, tạo môi trường bằng `python3 -m venv .venv`, kích hoạt bằng `source .venv/bin/activate`, rồi chạy các lệnh `pip` và `streamlit` ở trên.

Demo mặc định mở tại [localhost:8501](http://localhost:8501). Có thể chọn cổng khác:

```console
python -m streamlit run demo/app.py --server.port 8517
```

Phần giải bài toán và kiểm định nghiệm dùng thư viện chuẩn Python. [requirements.txt](requirements.txt) bổ sung thư viện cho giao diện, biểu đồ và kiểm thử. Dữ liệu mô phỏng được sinh trực tiếp nên có thể mở demo ngay.

## 2. Sử dụng giao diện demo

Mục **Chức năng** ở thanh bên có hai lựa chọn: **Mô phỏng** và **Đánh giá benchmark**.

### Mô phỏng

1. Chọn **Dữ liệu mô phỏng**, **Bộ dữ liệu Kris** hoặc **Tải dữ liệu JSON**.
2. Với dữ liệu mô phỏng, chọn bản đồ, số đơn, số nhân viên và sức chứa mỗi chuyến.
3. Bật **So sánh 5 thuật toán: B0, B2, LNS, ALNS, VNS** ngay trên nút chạy nếu muốn chạy đủ năm phương pháp; phần trợ giúp giải thích từng thuật toán. Mặc định chạy B0 và ALNS.
4. Trong **Nâng cao**, điều chỉnh seed, thời gian tìm kiếm và tiêu chí ưu tiên nếu cần. Có thể chọn vị trí chèn **Có hướng dẫn** và **Tăng tốc kiểm tra ứng viên**.
5. Bấm **Chạy tối ưu** để xem kết quả.

| Tab kết quả | Nội dung |
|---|---|
| Mô phỏng | Phát lại đường đi và hoạt động lấy hàng; đổi tốc độ, tua và chọn nhân viên. |
| Tổng quan | Quãng đường, thời gian hoàn tất, số đơn trễ và điểm mục tiêu. |
| Tuyến và lịch | Đường đi từng chuyến và lịch làm việc của nhân viên. |
| Chi tiết | Thông tin chuyến, đơn hàng và hàng hóa. |
| Đánh giá | So sánh thuật toán trên dữ liệu của lần chạy hiện tại, xem hội tụ và tải bảng/hình. |

Khi đổi cấu hình, bấm chạy lại để áp dụng. Tab **Đánh giá** ở đây phản ánh một lần chạy minh họa; kết quả thực nghiệm nhiều bài toán và seed nằm ở mục **Đánh giá benchmark**.

Giao diện được bố trí cho laptop 1366×768 và 1440×900. Nút chạy nằm trước **Nâng cao**;
tab chỉ dựng nội dung khi mở và giữ bộ lọc khi chuyển góc xem. Đổi tab
không chạy lại thuật toán. Ở tốc độ phát 1×, mô phỏng phát toàn bộ lịch trong
khoảng 30 giây; đồng hồ trên bản đồ là thời gian vận hành của phương án.
Tệp JSON đã mở được giữ trong phiên khi đổi chức năng; tên tệp và nút **Đóng tệp**
hiện khi quay lại. Remove hoặc Đóng tệp xóa dữ liệu đã tải khỏi phiên.

Giao diện luôn dùng **đơn vị mô phỏng** để quy đổi Kris nhất quán trên KPI, bản đồ, lịch,
bảng và biểu đồ: 10 đơn vị khoảng cách nguồn = 1 m; hệ số thời gian suy ra từ
vận tốc nguồn để tương ứng 60 m/phút như mô phỏng. Đây là quy ước minh họa chưa
hiệu chuẩn thực tế. Không cần chọn chế độ đơn vị. F, tỷ lệ cải thiện, số đơn trễ,
sức chứa và thời gian máy tính chạy thuật toán giữ nguyên. JSON luôn là dữ liệu
gốc; bảng đã quy đổi có hai nút tải CSV phân biệt đơn vị mô phỏng và đơn vị gốc.

### Đánh giá benchmark

Phần này mở được ngay cả khi chưa chạy mô phỏng:

1. Chọn **Đánh giá benchmark** trong **Chức năng**.
2. Tải tệp `report/evaluation.json` của một đợt benchmark lên, hoặc chọn **Báo cáo trên máy** nếu đã có kết quả trong `results/`.
3. Chọn **Nhóm dữ liệu** và **Thuật toán đối chứng** để xem bảng so sánh.
4. Trong tab **Biểu đồ**, chọn **Dùng cho → Báo cáo / Slide**, rồi chọn hình muốn xem. Có thể tải từng hình PNG và bảng CSV.

Gói `evaluation.json` chứa dữ liệu đầu vào và nghiệm để demo kiểm tra, tính lại các bảng. Chỉ cần mang tệp này sang máy khác; không cần sao chép thư mục dữ liệu gốc hoặc chạy lại thuật toán.

## 3. Chạy benchmark

Cấu hình thống nhất nằm trong [configs/benchmark.json](configs/benchmark.json). Cả năm thuật toán chạy trên cùng dữ liệu và trọng số. B0 và B2 chạy một lần cho mỗi bài toán; LNS, ALNS và VNS chạy qua nhiều seed ngẫu nhiên.

| Nhóm | Dữ liệu | Câu hỏi đánh giá |
|---|---|---|
| `maps` | Kho chuẩn, kho 2 khối, kho lớn, hạn giao gấp và phân khu ABC | Các thuật toán xử lý từng tình huống kho ra sao? |
| `scalability` | Dữ liệu tổng hợp, thay số đơn và giữ cấu hình kho, nhân viên, sức chứa cùng quy tắc sinh hạn | Chất lượng nghiệm và thời gian tính toán thay đổi thế nào theo quy mô? |
| `kris` | 18 bài toán Kris Small, gồm các nhóm 6, 12 và 18 đơn | Kết quả trên dữ liệu từ nguồn ngoài như thế nào? |

Năm bản đồ có điều kiện khác nhau nên không dùng riêng nhóm `maps` để kết luận ảnh hưởng của số đơn. Thí nghiệm quy mô dùng nhóm `scalability`.

### Chạy thử nhanh

```console
python -m src benchmark --config configs/benchmark.json --preset quick --groups maps scalability --output results/benchmark_quick_01 --presentation
```

Với cấu hình hiện tại, lệnh này chạy **7 bài toán chính, 56 lượt giải chính và 200 lượt khảo sát bổ sung**, tổng 256 lượt. Mỗi thuật toán tìm kiếm dùng 2 seed, tối đa 0,15 giây hoặc 30 vòng ở phần chính. Khảo sát quick dùng ngân sách 0,01/0,02/0,03 giây và cùng 2 seed. Quick dùng để kiểm tra luồng chạy, bảng và hình trước khi chạy đầy đủ.

### Chạy đầy đủ cho báo cáo và slide

```console
python -m src benchmark --config configs/benchmark.json --preset report --groups maps scalability kris --output results/benchmark_report_02 --presentation
```

Với cấu hình hiện tại, Report chạy **45 bài toán chính, 1.440 lượt giải chính và 765 lượt khảo sát bổ sung**, tổng **2.205 lượt**:

| Nhóm | Số bài toán | Số lượt giải |
|---|---:|---:|
| `maps` | 15 | 480 |
| `scalability` | 12 | 384 |
| `kris` | 18 | 576 |

Mỗi thuật toán tìm kiếm dùng 10 seed, tối đa 3 giây hoặc 100.000 vòng. Ngân sách này áp dụng riêng cho từng lượt, gồm khởi tạo và tìm kiếm. Thời gian toàn đợt còn có tiền xử lý, kiểm định và xuất hình; một bước đang xử lý có thể khiến lượt chạy vượt ngân sách.

Hai khảo sát bổ sung tự chạy bằng cùng lệnh: **ngân sách 0,5/3/6 giây** với trọng số cân bằng và **trọng số cân bằng/đường đi/độ trễ** tại 3 giây. Mỗi nhóm chọn trước tối đa ba input theo số đơn/tên; dùng cùng 5 seed giữa các điều kiện. Điều kiện cân bằng 3 giây dùng chung cho hai khảo sát. Tổng ngân sách tìm kiếm cấu hình khoảng 102,4 phút; đây không phải dự báo thời gian thực tế. Khảo sát có tính thăm dò, không thay thế benchmark chính. Cấu hình ở `sensitivity` trong JSON; đặt `enabled: false` để chủ động bỏ cả hai.

Nhóm `kris` cần [catalog](data/processed/kris_small/catalog.json) và các JSON được liệt kê trong đó. Nếu thiếu dữ liệu, chuẩn bị theo [hướng dẫn dữ liệu](data/README.md), hoặc chạy riêng `--groups maps scalability`. Khi đã chọn rõ `kris`, thiếu dữ liệu sẽ được báo trước khi giải.

### Kiểm tra cấu hình trước khi chạy

```console
python -m src benchmark --config configs/benchmark.json --preset report --groups maps scalability kris --dry-run
```

`--dry-run` kiểm tra dữ liệu và in số bài toán, số lượt giải; không chạy thuật toán và không ghi kết quả.

### Tiếp tục đợt bị ngắt

Giữ nguyên lệnh, cấu hình, dữ liệu và phiên bản mã nguồn; thêm `--resume`:

```console
python -m src benchmark --config configs/benchmark.json --preset report --groups maps scalability kris --output results/benchmark_report_02 --resume --presentation
```

Runner dùng lại **nhóm đã hoàn thành và qua kiểm định**. Nhóm chạy dở được chạy lại từ đầu, còn dữ liệu dở dang được giữ trong `_attempts/`. Đây là cách tiếp tục theo nhóm dữ liệu, không tiếp tục từng lượt hoặc từng vòng tìm kiếm.

Thư mục đầu ra của đợt mới phải mới hoặc rỗng; đổi hậu tố `01`, `02`, … cho mỗi đợt. Giữ nguyên thư mục kết quả trong lúc chạy. Sau khi sửa mã nguồn, dữ liệu hoặc cấu hình, tạo đợt mới để các kết quả cùng một phiên bản.

### Xuất lại hình từ kết quả đã lưu

```console
python -m src report --input results/benchmark_report_02 --output results/benchmark_png_02/report --presentation
```

Lệnh `report` kiểm tra bằng chứng rồi xuất lại bảng và hình, **không chạy lại thuật toán**. Đầu vào có thể là thư mục benchmark đã hoàn thành hoặc tệp `evaluation.json`; đầu ra phải là thư mục mới hoặc rỗng.

Dùng lệnh này khi muốn cập nhật cách trình bày hình, hoặc bổ sung bộ ảnh slide cho đợt đã chạy xong. `--resume` của đợt hoàn chỉnh giữ báo cáo đã có.

| Tùy chọn | Tác dụng |
|---|---|
| `--preset quick` / `--preset report` | Chọn chạy thử hoặc chạy đầy đủ. |
| `--groups maps scalability kris` | Chọn nhóm dữ liệu; có thể chỉ truyền một hoặc hai nhóm. |
| `--presentation` | Tạo thêm bộ PNG cho slide, khung 16:9 và chữ lớn. |
| `--no-charts` | Xuất bảng CSV, JSON và tài liệu, bỏ bước vẽ ảnh. |
| `--dry-run` | Kiểm tra và đếm lượt trước khi chạy benchmark. |
| `--resume` | Dùng lại các nhóm đã hoàn thành của đợt bị ngắt. |

Đổi seed, trọng số hoặc ngân sách tìm kiếm trong `configs/benchmark.json`; lệnh benchmark không có tham số `--seconds` riêng.

## 4. Lấy bảng và ảnh cho báo cáo, slide

Sau khi benchmark hoàn thành, kết quả có cấu trúc:

```text
results/benchmark_report_02/
├── config.json
├── preregistered.json
├── manifest.json
├── evaluation.json
├── datasets/
│   ├── maps/
│   ├── scalability/
│   ├── kris/
│   └── *_sensitivity_*/
└── report/
    ├── index.html
    ├── REPORT.md
    ├── summary.csv
    ├── per_instance.csv
    ├── raw_metrics.csv
    ├── sensitivity.csv
    ├── evaluation.json
    ├── availability.json
    ├── figures_report/
    │   ├── 01_maps/
    │   ├── 02_scalability/
    │   └── 03_kris/
    └── figures_presentation/
        ├── 01_maps/
        ├── 02_scalability/
        └── 03_kris/
```

Ví dụ trên chọn đủ ba nhóm và bật `--presentation`. Mở **`report/index.html`** bằng trình duyệt để xem ảnh thu nhỏ, đọc chú thích và chọn hình; trang dùng được khi không có mạng.

| Cần dùng | Lấy ở đâu |
|---|---|
| Bảng tổng hợp so sánh thuật toán và đối chứng B0/B2 | `summary.csv` |
| Trung bình và độ lệch chuẩn theo từng bài toán, thuật toán | `per_instance.csv` |
| Chỉ tiêu của từng lượt giải | `raw_metrics.csv` |
| Ngân sách, trọng số, thời gian thực đo và thống kê seed cho hai khảo sát | `sensitivity.csv` |
| Ảnh chèn vào báo cáo | `figures_report/` |
| Ảnh chèn vào slide | `figures_presentation/` |
| Gói tải lên demo | `evaluation.json` |
| Cách đọc kết quả và liên kết hình | `REPORT.md` |

**Ảnh xuất ra chỉ có PNG, 300 dpi, mỗi ảnh một biểu đồ.** Bộ slide dùng khung 16:9; lệnh không tạo tệp PowerPoint. Cả hai bộ dùng cùng số liệu và màu thuật toán.

Có bảy nhóm hình khi chạy cấu hình mới: **chất lượng F**, **các chỉ số thành phần**, **độ ổn định**, **hội tụ**, **ảnh hưởng của quy mô**, **độ nhạy ngân sách** (`06_do_nhay_ngan_sach_vi_du_*.png`) và **đánh đổi theo trọng số** (`07_danh_doi_trong_so_vi_du_*.png`). Hai nhóm mới xuất riêng cho từng input được chọn, trong thư mục nhóm chính; râu là SD giữa seed. Hình trọng số so quãng đường–tổng trễ, không so F khác trọng số hoặc khẳng định biên Pareto tối ưu. Một nhóm có thể tạo nhiều ảnh. Nếu thiếu dữ liệu hoặc điều kiện thí nghiệm chưa phù hợp, lý do nằm trong danh mục và `availability.json`. Kết quả cũ không có các điều kiện bổ sung vẫn mở/xuất được bộ hình cũ; chỉ đổi kiểu vẽ không tạo được dữ liệu độ nhạy mới.

Các bảng lấy trung bình qua seed trên từng bài toán trước khi tổng hợp theo nhóm. Độ lệch chuẩn mô tả dao động, không thay cho kiểm định ý nghĩa thống kê. Chi tiết cách tính và điều kiện vẽ hình nằm trong [docs/EVALUATION.md](docs/EVALUATION.md).

## 5. Giải một bài toán bằng dòng lệnh

Sinh dữ liệu, giải bằng ALNS rồi kiểm tra nghiệm:

```console
python -m src generate --scenario double_block --orders 20 --pickers 4 --capacity 30 --seed 42 --output data/synthetic/example.json
python -m src solve data/synthetic/example.json --method ALNS --seconds 3 --iterations 100000 --seed 42 --output results/example/solution.json
python -m src validate data/synthetic/example.json results/example/solution.json
```

Chọn tiêu chí ưu tiên bằng `--profile`:

| Giá trị | Ưu tiên | Trọng số: quãng đường / thời gian hoàn tất / tổng độ trễ |
|---|---|---|
| `balanced` | Cân bằng, mặc định | 1/3 · 1/3 · 1/3 |
| `distance` | Quãng đường | 0,6 · 0,2 · 0,2 |
| `makespan` | Thời gian hoàn tất | 0,2 · 0,6 · 0,2 |
| `tardiness` | Tổng độ trễ | 0,2 · 0,2 · 0,6 |

Có thể dùng `--weights 0.5 0.3 0.2` thay cho `--profile`. Ba trọng số phải dương, hữu hạn và có tổng bằng 1. Lệnh `solve` mặc định giới hạn 200 vòng; truyền `--iterations` nếu muốn dùng ngân sách thời gian dài hơn.

Thử biến thể mới bằng `--candidate-policy guided --incremental-validation`.
Để kiểm tra tính tái lập theo số vòng, dùng `--seconds 0 --iterations 200`
và cùng seed/input/config. Với ngân sách giây, tải máy có thể làm số vòng và
nghiệm khác dù seed giống nhau. Guided chỉ xếp hạng ứng viên; không bảo đảm
thắng uniform hoặc VNS trên mọi bài.

Với dữ liệu nhỏ, dùng bộ giải exact:

```console
python -m src exact data/synthetic/tiny_4.json --output results/example/exact.json
```

Exact giới hạn tối đa 6 đơn và 8 vị trí hàng ngoài điểm xuất phát. Chỉ xem nghiệm là được chứng nhận tối ưu khi kết quả có `certified_optimal=true`.

Tra cứu đầy đủ tham số:

```console
python -m src --help
python -m src solve --help
python -m src benchmark --help
python -m src report --help
```

## 6. Mô hình và thuật toán

Mỗi đơn thuộc đúng một chuyến, tải trọng chuyến không vượt sức chứa. Chuyến bắt đầu và kết thúc tại điểm xuất phát, di chuyển trên đồ thị kho. Nhân viên thực hiện các chuyến lần lượt; các đơn trong chuyến hoàn thành khi nhân viên trở về.

Điểm **F** là tổng có trọng số của **quãng đường**, **thời gian hoàn tất toàn bộ công việc** và **tổng độ trễ**, sau khi chuẩn hóa theo B0. **F càng nhỏ càng tốt** khi so trên cùng bài toán và trọng số. Mô hình dùng hạn giao mềm: đơn có thể trễ nhưng độ trễ được tính vào mục tiêu. Giảm tổng độ trễ không bảo đảm giảm số đơn trễ.

Chuẩn tham chiếu là `D_ref = max(D_B0, 1)`, `C_ref = max(C_B0, 1)` và `T_ref = n × C_ref`, với `n` là số đơn.

| Thuật toán trong benchmark | Cách giải |
|---|---|
| B0 | Gom đơn theo thứ tự `rank`, chọn đường bằng nearest neighbor; xếp chuyến theo hạn giao sớm nhất trong chuyến rồi giao cho nhân viên rảnh sớm nhất. |
| B2 | Gom đơn tham lam và cải thiện đường đi bằng 2-opt. |
| LNS | Bỏ một phần đơn khỏi nghiệm rồi chèn lại để tìm cách gom và phân công tốt hơn. |
| ALNS | Dùng khung LNS, điều chỉnh xác suất chọn toán tử theo hiệu quả tìm kiếm. |
| VNS | Thay đổi cấu trúc lân cận để cải thiện cách gom đơn và lịch nhân viên. |

CLI còn hỗ trợ các phương pháp bổ sung; xem `solve --help` và [ghi chú thuật toán](docs/ALGORITHM_NOTES.md).

Các đơn có sẵn từ thời điểm 0 và nhân viên đồng nhất. Mô hình hiện chưa xét đơn phát sinh trong lúc chạy, va chạm giữa nhân viên hoặc ca nghỉ. Dữ liệu Kris giữ đơn vị nguồn trong benchmark; quy đổi mét/thời gian của phần mô phỏng chỉ là quy ước hiển thị, không thay số liệu thực nghiệm. Xem [nguồn dữ liệu và giới hạn so sánh](data/README.md).

## 7. Cấu trúc mã nguồn

```text
demo/
  app.py                  # Khởi chạy giao diện
  components.py           # Điều khiển và hiển thị kết quả mô phỏng
  simulation.py           # Mô phỏng động
  state.py                # Chuẩn bị dữ liệu và quản lý lần chạy
  evaluation.py           # Đánh giá lần chạy và mở benchmark
  display.py              # Quy đổi lớp trình bày, kiểm định bằng chứng nguồn trước
src/
  cli.py                  # Các lệnh generate, solve, validate, exact, benchmark, report
  generator.py            # Sinh dữ liệu và năm kịch bản kho
  solver.py               # Điều phối các thuật toán
  search.py               # LNS và ALNS
  vns.py                  # VNS
  exact.py                # Bộ giải exact cho bài toán nhỏ
  evaluator.py            # Tính lịch và mục tiêu
  validator.py            # Kiểm định nghiệm độc lập
  experiment.py           # Chạy benchmark theo nhóm, khóa cấu hình và tiếp tục đợt bị ngắt
  benchmark.py            # Chạy từng nhóm và lưu nghiệm gốc
  evaluation.py           # Kiểm tra gói đánh giá và tổng hợp chỉ tiêu
  evaluation_report.py    # Xuất CSV, JSON, PNG và danh mục hình
  evaluation_figures.py   # Điểm gọi chung cho các biểu đồ
  evaluation_charts/
    quality.py            # Chất lượng F
    components.py         # Các chỉ số thành phần
    stability.py          # Độ ổn định
    convergence.py        # Hội tụ
    scalability.py        # Ảnh hưởng của quy mô
    common.py             # Màu, nhãn và hàm dùng chung
configs/                  # Cấu hình chạy
data/                     # Dữ liệu đầu vào
docs/                     # Tài liệu mô hình, thuật toán và đánh giá
scripts/                  # Công cụ hỗ trợ và kiểm tra
tests/                    # Kiểm thử
results/                  # Kết quả sinh khi chạy, được Git bỏ qua
```

Muốn sửa một nhóm biểu đồ, chỉnh file tương ứng trong `src/evaluation_charts/`. Sau đó dùng lệnh `report` để xuất hình từ kết quả đã lưu.

## 8. Kiểm thử và tài liệu

```console
python -m pytest -q
```

Các kiểm thử bao phủ thuật toán, ràng buộc nghiệm, dữ liệu, benchmark, xuất báo cáo, trạng thái demo và đơn vị hiển thị. Khi thay đổi thuật toán hoặc cách tính mục tiêu, chạy kiểm thử và tạo đợt benchmark mới.

- [Mô hình và cách diễn giải kết quả](docs/MODEL_AND_DEFENSE.md)
- [Thuật toán, bất biến và bộ giải exact](docs/ALGORITHM_NOTES.md)
- [Quy tắc benchmark và đánh giá](docs/EVALUATION.md)
- [Thiết kế giao diện laptop và quy ước Kris](docs/STREAMLIT_LAPTOP_PLAN_2026-10-11.md)
- [Định dạng dữ liệu JSON](docs/SCHEMA.md)
- [Nguồn dữ liệu Kris và giới hạn sử dụng](data/README.md)

Dự án phục vụ học tập và nghiên cứu. Repository hiện chưa có tệp `LICENSE`.

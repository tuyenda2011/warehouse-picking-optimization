# Benchmark và đánh giá dùng chung

Một bộ giải sinh bằng chứng gốc, validator kiểm lại tải/tuyến/lịch/chỉ tiêu, sau đó các
hàm trong `src/evaluation.py` tổng hợp dữ liệu cho CSV, bộ hình và giao diện Streamlit.
Việc xuất hoặc mở báo cáo không chạy lại thuật toán.

Thư mục đầu ra phải được giữ nguyên trong suốt đợt chạy. Runner kiểm tra các tệp
cấu hình, bài toán hiện tại và thư mục kết quả quanh mỗi lượt; nếu chúng bị mất,
thay đổi hoặc thay thế, tiến trình dừng và báo đường dẫn gặp lỗi. Sau khi bắt đầu
chạy, runner không tự tạo lại thư mục dữ liệu đã mất để tiếp tục ghi kết quả.
Không xóa hoặc dọn `results/` khi benchmark còn chạy. `--resume` vẫn chỉ tái sử dụng
nhóm đã hoàn thành và qua kiểm tra; nó không tái tạo những kết quả gốc đã bị xóa.

## Dữ liệu và protocol

`configs/benchmark.json` có preset quick/report và ba nhóm maps/scalability/kris.
Trọng số và cách chuẩn hóa F cố định trong từng instance. Đối chứng B0/B2 chỉ thay
phép so sánh, không thay hàm mục tiêu. Hạn mềm cho phép có đơn trễ trong nghiệm hợp lệ.
Các thuật toán tìm kiếm dùng cùng ngân sách gồm khởi tạo và tìm kiếm; thời gian tổng
còn bao gồm tiền xử lý và kiểm định. Một thao tác đang chạy có thể vượt ngân sách.

Quick dùng để kiểm tra chức năng, không chứng minh chất lượng tổng quát. Report dùng
nhiều instance và seed; tham số tìm kiếm phải được chọn trước khi đọc kết quả đánh giá.
Các nhóm có dữ liệu, đơn vị và điều kiện khác nhau luôn được giữ riêng.

Scalability giữ cấu hình kho, nhân viên, sức chứa và quy tắc sinh dữ liệu/hạn cố định
khi thay số đơn. Horizon sinh hạn có thể thay đổi theo số đơn dù quy tắc/tightness cố
định; vì vậy kết luận áp dụng cho protocol sinh hạn đó, không phải hạn tuyệt đối cố định.

## Đơn vị thống kê

- Lấy trung bình search seed trong từng instance, rồi so sánh cặp trên cùng instance.
- B0/B2 tất định chạy một lần; không nhân bản thành nhiều quan sát.
- `per_instance.csv`: metric std là độ lệch chuẩn giữa search seed.
- `summary.csv`: mức cải thiện trung bình và spread giữa các trung bình instance;
  spread này không phải khoảng tin cậy hay kiểm định ý nghĩa thống kê.
- Cùng seed nhu cầu qua nhiều kích thước tạo tương quan. Nếu bổ sung suy luận thống
  kê, cần bootstrap theo nhóm seed nhu cầu, không bootstrap từng hàng run.
- Đối chứng bằng 0: phần trăm để trống và dùng chênh lệch tuyệt đối. Có cột số instance
  đủ điều kiện tính phần trăm để mẫu số không bị che giấu.
- Win/tie/loss theo F với sai số tuyệt đối 1e-9, không phải kết luận có ý nghĩa thống kê.

## Bảy nhóm hình

1. Chất lượng: cải thiện F so với đối chứng, trung bình seed trước khi so sánh.
2. Thành phần: quãng đường, thời gian hoàn tất và tổng độ trễ; thể hiện cả đánh đổi.
3. Ổn định: phân bố các seed trên instance chọn cố định trước theo metadata/tên;
   không chọn instance hoặc seed theo thuật toán thắng.
4. Hội tụ: best-so-far F theo thời gian thực gồm khởi tạo; các đường nhiều seed chỉ
   tổng hợp trong khoảng thời gian chung thực sự đã quan sát. Không lấp thời gian
   trước khởi tạo hoặc kéo dài trace ngắn như thể đã đo được.
5. Quy mô: chất lượng và thời gian tính toán theo số đơn trên nhóm dữ liệu có điều
   kiện được kiểm soát. Năm bản đồ demo khác nhau không thay thế thí nghiệm này.
6. Ngân sách: F cuối cùng theo 0,5/3/6 giây với trọng số cân bằng; cùng input/seed
   giữa các điều kiện. Điểm là trung bình seed, râu là SD. Trục x là ngân sách yêu
   cầu; thời gian thực đo và số lượt 0 vòng có trong `sensitivity.csv`.
7. Trọng số: quãng đường–tổng độ trễ theo profile cân bằng/đường đi/độ trễ,
   cùng ngân sách 3 giây. Râu ngang/dọc là SD; không so F giữa trọng số và không
   gọi tập điểm quan sát là biên Pareto tối ưu. Điểm trùng nhau có thể chồng nhau.

Hai nhóm mới cần chạy cấu hình `sensitivity` đã tích hợp vào cùng lệnh benchmark.
Report chọn trước tối đa ba input mỗi nhóm theo số đơn/tên, năm seed tìm kiếm
1–5; điều kiện cân bằng 3 giây dùng chung. Các điều kiện/lượt giải bổ sung chạy
tuần tự theo thứ tự xáo với seed cố định, được khóa nguồn/cấu hình/input cùng
benchmark chính. Tổng 765 lượt bổ sung cho ba nhóm; không gộp vào 1.440 lượt
chính khi diễn giải. Đây là khảo sát thăm dò trên tập được chọn, không suy luận
cho mọi kho; tải máy vẫn có thể ảnh hưởng kết quả theo thời gian.
Quick dùng hai seed và ngân sách 0,01/0,02/0,03 giây để kiểm tra pipeline.
Nhóm điều kiện lưu trong `datasets/*_sensitivity_*/`; Streamlit giữ bộ chọn ba
nhóm chính, đưa hai hình vào mục **Biểu đồ** và cung cấp CSV độ nhạy riêng.
Gói cũ thiếu thiết kế độ nhạy chỉ xuất năm nhóm hình cũ. Không suy diễn dữ liệu
trọng số từ trace hoặc chạy âm thầm khi mở báo cáo. Thiết kế chi tiết tại
[BENCHMARK_SENSITIVITY_DESIGN.md](BENCHMARK_SENSITIVITY_DESIGN.md).

Hình giữ màu, marker và cách tính nhất quán. Cả hai kiểu chỉ xuất PNG 300 dpi,
mỗi ảnh chứa một biểu đồ. Kiểu report dùng chữ phù hợp tài liệu; kiểu presentation
giữ khung 16:9 và dùng chữ lớn. Hình chất lượng chia trang tối đa 9 bài toán cho
báo cáo và 6 bài toán cho slide. Hình thiếu dữ liệu được ghi trong availability.json
và danh mục hình thay vì tạo số liệu giả.

Biểu đồ bản đồ lấy tên kho từ `metadata.scenario.id`, kèm số đơn và seed dữ liệu,
ví dụ **Kho 2 khối · 30 đơn · seed 42**. Tên tệp đầu vào có thể thay đổi mà tên kho
vẫn giữ đúng. Mã bài toán gốc được giữ trong CSV, JSON và chú thích để tra lại số liệu.

## Mở và xuất bộ hình

Mở `report/index.html` bằng trình duyệt để xem ảnh thu nhỏ và chọn từng PNG; trang
hoạt động khi không có mạng. Hình nằm trong `figures_report/` và, nếu bật
`--presentation`, `figures_presentation/`. Khi chọn đủ ba nhóm, mỗi thư mục có
`01_maps/`, `02_scalability/`, `03_kris/`. `REPORT.md` giữ phần giải thích ngắn gọn và
liên kết hình; cấu hình đầy đủ vẫn nằm trong `evaluation.json`. Các bảng CSV và
bằng chứng gốc không thay đổi khi xuất lại hình.

Ví dụ xuất lại kết quả đã phục hồi, không chạy lại thuật toán:

```text
python -m src report --input results/benchmark_report_01_recovered --output results/benchmark_png_01/report --presentation
```

Luôn dùng thư mục xuất mới. `--no-charts` chỉ xuất bảng và gói JSON, không sinh PNG.

## Mã nguồn tạo hình

Mỗi nhóm biểu đồ có mô-đun riêng để sửa nội dung hoặc cách vẽ:

```text
src/evaluation_charts/
  quality.py       # Chất lượng F so với đối chứng
  components.py    # Quãng đường, thời gian hoàn tất, tổng độ trễ
  stability.py     # Dao động giữa các seed
  convergence.py   # Hội tụ theo thời gian đã ghi
  scalability.py   # Chất lượng và thời gian theo quy mô có kiểm soát
  sensitivity.py   # Ngân sách yêu cầu và đánh đổi vận hành theo trọng số
  common.py        # Màu, nhãn và các hàm vẽ dùng chung
```

`src/evaluation_figures.py` giữ API dùng chung cho demo và báo cáo, chọn mô-đun
tương ứng rồi trả danh mục hình. `src/evaluation_report.py` xuất PNG, bảng CSV,
gói JSON, hướng dẫn và trang danh mục. Các lệnh benchmark/report ở trên giữ nguyên.

## Gói mở trong demo

`evaluation.json` schema_version=1 chứa config, instance đầy đủ, inventory fingerprint
và nghiệm/thời gian/trace của từng run. Bảng tổng không phải nguồn sự thật; các số
được dựng lại khi mở gói. Không đọc bất kỳ đường dẫn máy nguồn nào trong file tải lên.

Validator phát hiện thiếu/trùng run, seed sai, fingerprint sai, sai mục tiêu, tuyến
không hợp lệ và trace không nhất quán. Việc này chứng minh tính nhất quán nội bộ;
không xác thực danh tính tác giả của file hay đo lại runtime trên máy người xem.

Giao diện có workspace benchmark độc lập với mô phỏng. Bằng chứng đầu vào và nghiệm
gốc được kiểm định trước khi tạo bảng trình bày. Giao diện luôn áp dụng **đơn vị mô phỏng**
quy ước Kris cho cả mô phỏng, đánh giá lần chạy và bảng/biểu đồ benchmark: 0,1 m mỗi
đơn vị khoảng cách nguồn, thời gian suy ra theo vận tốc nguồn để khớp mô phỏng
60 m/phút. Đây là minh họa chưa hiệu chuẩn vật lý. Không có lựa chọn đổi chế độ đơn vị.
F, tỷ lệ, số đếm, sức chứa và runtime máy tính không đổi; JSON nguồn vẫn giữ nguyên.
CSV đã quy đổi và CSV đơn vị gốc có nút tải/tên tệp riêng. Các biểu đồ chỉ số vận hành
hiển thị trung bình và độ lệch chuẩn giữa seed, không phải khoảng tin cậy. Nguồn
benchmark và bộ hình do CLI xuất vẫn dùng đơn vị nguồn.
Chọn **Đánh giá benchmark** trong mục **Chức năng** ở thanh bên, rồi tải gói lên
hoặc chọn **Báo cáo trên máy**. Dùng **Nhóm dữ liệu** và **Thuật toán đối chứng** để
lọc kết quả. Tab **Biểu đồ** có mục **Dùng cho** (**Báo cáo** / **Slide**) và
**Chọn biểu đồ** để mở từng hình.

## Checkpoint và phiên bản

Mỗi đợt khóa cấu hình đã resolve, mã nguồn và input trước khi giải. Nhóm hoàn chỉnh
được audit rồi chuyển vào datasets/. Resume chỉ dùng lại nhóm có hash và cấu hình
khớp; attempt dở dang được giữ lại và nhóm đó chạy lại. Xuất report vào thư mục mới
cho phép dùng bằng chứng lịch sử mà không buộc source hiện tại trùng source khi chạy.

Sau khi thay trọng số, dữ liệu hoặc thuật toán, tạo đợt experiment mới. Không gộp
nghiệm của hai phiên bản vào cùng bảng và không sửa các file bằng chứng đã khóa.

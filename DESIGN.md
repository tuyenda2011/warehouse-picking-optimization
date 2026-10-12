---
name: Warehouse Workspace
colors:
  primary: "#176B5B"
  surface: "#FFFFFF"
  neutral: "#F5F7F6"
  on-surface: "#1C302B"
  muted: "#53665F"
  border: "#DCE5E0"
  error: "#B42318"
  warning: "#8A5210"
typography:
  headline-lg: {fontFamily: "sans-serif", fontSize: 28px, fontWeight: 650, lineHeight: 1.2}
  headline-md: {fontFamily: "sans-serif", fontSize: 22px, fontWeight: 600, lineHeight: 1.3}
  body-md: {fontFamily: "sans-serif", fontSize: 16px, fontWeight: 400, lineHeight: 1.5}
  body-sm: {fontFamily: "sans-serif", fontSize: 14px, fontWeight: 400, lineHeight: 1.4}
rounded: {sm: 4px, md: 8px}
spacing: {xs: 4px, sm: 8px, md: 16px, lg: 24px, xl: 32px}
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    height: 40px
---

# Warehouse Workspace

## Overview

Giao diện Streamlit phục vụ thao tác và thuyết trình trên laptop. Hai kích thước
kiểm tra chính là 1366×768 và 1440×900. Ưu tiên bản đồ, bảng và biểu đồ trong vùng
nội dung; cấu hình đặt ở thanh bên. Giữ font sans-serif của giao diện, hỗ trợ tiếng Việt.

## Colors

Một màu xanh đậm cho hành động chính. Nền trắng và thanh bên trung tính. Màu nhân
viên nhất quán giữa bản đồ và lịch, luôn có nhãn chữ. Cảnh báo dành cho trạng thái
hoặc giới hạn thực nghiệm cần chú ý.

## Typography

Tiêu đề ngắn, nội dung 16px, chú thích 14px. Chỉ số dùng chữ số có chiều rộng bằng
nhau. Giữ đơn vị cạnh số liệu; không thay nhãn bằng biểu tượng.

## Layout

Thanh bên khoảng 300px. Vùng nội dung tận dụng chiều rộng còn lại, tối đa 1440px,
với khoảng đệm gọn; đệm trên 3,5rem để tiêu đề nằm dưới header cố định của Streamlit.
Chọn phương án và tải kết quả cùng hàng. Ba chỉ số chính nằm
trên hàng kế tiếp, rồi đến các tab và bản đồ. Mô phỏng có chiều cao phù hợp viewport
laptop. Các bộ chọn biểu đồ dùng cùng một hàng; bảng cuộn trong vùng riêng.

Ở màn 1366×768, giảm phần đệm đầu trang và giữ vùng bản đồ khoảng 360–440px,
không để toolbar hoặc danh sách nhân viên đẩy bản đồ ra khỏi vùng đọc. Bảng chi
tiết có chiều cao khoảng 320px. Bộ lọc nhân viên và chuyến đặt cùng hàng.

## Elevation & Depth

Dùng khoảng cách và đường phân chia nhẹ, không thêm thẻ trang trí quanh mọi vùng.
Không lặp lại tiêu đề đã nằm trong tab hoặc trong hình.

## Shapes

Giữ điều khiển native của Streamlit, bo góc 8px và focus rõ khi dùng bàn phím.

## Components

- Thanh bên chỉ hiển thị trường của nguồn đang dùng. Mô tả kịch bản nằm trong help.
  Số đơn và nhân viên cùng hàng; seed, ngân sách, trọng số và reset ở Nâng cao.
- Một nút Chạy tối ưu ở thanh bên, đặt trước Nâng cao để luôn dễ tìm.
  Ô **So sánh 5 thuật toán: B0, B2, LNS, ALNS, VNS** nằm ngay trước nút chạy,
  ngoài Nâng cao; phần trợ giúp giải thích từng thuật toán và ngân sách riêng.
  Trạng thái chưa chạy chỉ cần tóm tắt dữ liệu và
  một câu hướng dẫn. Thay cấu hình có một thông báo yêu cầu chạy lại.
- Mô phỏng hiển thị một dòng nhận diện dữ liệu của snapshot và ba KPI. Giữ lưu ý
  quy đổi Kris gần KPI. JSON tải xuống giữ dữ liệu gốc.
- Quy đổi Kris dùng cùng quy ước cho mô phỏng, KPI, lịch, bảng và biểu đồ đánh
  giá, luôn áp dụng và không có ô chọn chế độ đơn vị. Mốc là vận tốc mặc định
  của mô phỏng (60 m/phút); giả định khoảng cách
  10 đơn vị nguồn = 1 m phải được công khai. Đây là quy ước minh họa, chưa phải
  hiệu chuẩn kho thực. Đơn vị tải nguồn và thời gian chạy thuật toán giữ nguyên.
- Phương án có F thấp nhất chỉ được nhận diện trong các phương án của lần chạy
  hiện tại; không dùng nhãn ngụ ý tốt nhất trên mọi dữ liệu.
- Tabs theo dõi lựa chọn và chỉ dựng nội dung đang mở. Giữ các bộ lọc khi tab bị
  ẩn; chuyển tab không chạy lại bộ giải.
- Toolbar mô phỏng gồm hai hàng rõ ràng. Đồng hồ vận hành luôn tách khỏi tốc độ
  phát: 1× là phát nhanh toàn bộ lịch trong khoảng 30 giây, không là thời gian thực.
  Nhãn trạng thái nhân viên 13–14px; nhiều nhân viên có vùng cuộn riêng.
- Phân tích F, trọng số và hội tụ nằm tại Đánh giá; Tổng quan không lặp phân tích.
  Đánh giá luôn đọc snapshot gốc và nhắc ngắn đây là một bài toán/một seed.
- Benchmark cho chọn gói JSON hoặc báo cáo local. Bảng hiện ngay dưới bộ lọc; seed,
  ngân sách, trọng số và cách tổng hợp nằm trong mục mở rộng. Quick có một lưu ý ngắn.
- Biểu đồ không có tiêu đề DOM lặp tiêu đề trong ảnh. Chú thích và cách tính nằm
  trong mục mở rộng; nút tải PNG vẫn hiện cạnh vùng hình.
- Benchmark luôn trình bày Kris bằng đơn vị mô phỏng. CSV quy đổi và CSV nguồn
  được đặt tên rõ; các tỷ lệ cải thiện và F không thay đổi.
- Giữ thông báo lỗi và lý do không đủ dữ liệu. Không hiển thị kết quả cũ khi tệp mới
  không hợp lệ. Các bộ lọc chỉ đổi góc nhìn, không chạy lại thuật toán.

## Do's and Don'ts

Giữ nhãn, đơn vị, dữ liệu gốc và khả năng dùng bàn phím. Dùng tên kho thay mã kỹ thuật
khi có metadata kịch bản. Không dùng các đoạn hướng dẫn dài để lấp vùng trống. Kiểm
tra laptop trước khi thêm điều chỉnh cho kích thước khác.

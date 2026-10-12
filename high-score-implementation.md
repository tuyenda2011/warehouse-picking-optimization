# Triển khai nâng chất lượng — 10/10/2026

Người dùng đã đồng ý triển khai lộ trình. Chất lượng được đánh giá theo bằng chứng thực đo; không đặt điều kiện chỉ giữ kết quả tốt cho ALNS.

- [x] Sao lưu source, cấu hình, báo cáo và gói nộp tại `tmp/high-score-before-20261010`.
- [x] Thống nhất inventory source đệ quy và đường dẫn tương đối.
- [x] Tách tên hiển thị instance khỏi filename không an toàn; kiểm tra inventory archive.
- [x] Kiểm thử đầy đủ: 339 test sau sửa nền tảng; cuối cùng 345 passed, 1 warning, 180,48 giây, gồm demo mới/runner/bootstrap.
- [x] Profile n=20,100,200 và quyết định cải tiến sau khi có số đo.
- [x] Triển khai `candidate_policy=guided` có đối chứng `uniform`; mặc định giữ cũ.
- [x] Kiểm chứng tính đúng, tính tái lập, cached/full và đối chiếu exact trong regression tests.
- [x] Pilot/ablation: 456 lượt, giữ mọi kết quả; toàn bộ đã kiểm chứng sau sửa audit tuple/list bằng driver niêm phong riêng.
- [x] Khóa source/config/selection trước holdout mới; cả amendment audit được khóa khi chưa có run holdout.
- [x] Chạy 36 instance holdout × 10 seed × 4 phương pháp tìm kiếm, cộng B0/B2: đủ 1.512 lượt, mọi nghiệm hợp lệ.
- [x] Phân tích theo đơn vị instance và tạo biểu đồ có độ bất định: hiệu ứng chính 0,556%, khoảng 95% [0,406%; 0,706%], chưa đạt ngưỡng 1%.
- [x] Cập nhật báo cáo, giả mã, giới hạn, 23 câu hỏi bảo vệ và đánh giá: code 9,4; ý tưởng 9,0; báo cáo 9,5 (tham khảo).
- [x] Biên dịch/render/kiểm tra PDF 73 trang và đóng gói đủ bằng chứng mới: 4.038 tệp payload qua CRC/SHA256, dữ liệu lịch sử và 115 tệp sao lưu còn nguyên.

Hoàn tất ngày 11/10/2026. Full suite cuối đạt 345 test; ba luồng Edge
headless đạt. Điểm tham khảo code/ý tưởng trung bình 9,2; không chấm phần
bảo vệ chưa quan sát. Hồ sơ số liệu và đánh giá nằm trong
`report/generated/upgrade`, gói cuối là `report.zip`.

Kết quả cũ giữ nguyên. Sau thay đổi thuật toán, báo cáo phải gắn rõ phiên bản với kết quả. Các run search thực nghiệm chạy tuần tự, không cạnh tranh CPU với pytest hoặc profiling. Nguồn skill K-Dense được ghi nhận trong báo cáo và tài liệu thực nghiệm.

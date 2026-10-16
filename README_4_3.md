# Smart Class 4.3 – bản thử nghiệm

## Thay đổi
- Ngày/giờ thông báo và xác nhận đọc hiển thị theo `Asia/Ho_Chi_Minh` (UTC+7), định dạng Việt Nam. PostgreSQL tiếp tục lưu `TIMESTAMPTZ` theo thời điểm tuyệt đối; không cộng thêm 7 giờ vào dữ liệu.
- Admin và giáo viên được phân công lớp có thể **ẩn/xóa mềm** thông báo cũ (ghi audit log); tệp R2 và lịch sử vẫn được lưu để kiểm toán. Không có xóa vĩnh viễn thông báo trong bản này.
- Khi tạo thông báo, giáo viên chọn toàn lớp hoặc chọn một/nhiều học sinh. Chỉ tài khoản phụ huynh đang liên kết với học sinh được chọn nhận và xem thông báo riêng; API kiểm tra quyền ở danh sách, xác nhận đọc, tệp đính kèm và Web Push. Không có tài khoản học sinh trong hệ thống nên thông báo riêng được gửi **cho phụ huynh của học sinh được chọn**, không gửi trực tiếp cho học sinh.

## Triển khai an toàn
1. Sao lưu PostgreSQL 4.2 và kiểm tra khả năng phục hồi trên DB riêng. Giữ bản 4.2 đang hoạt động.
2. Tạo branch `smart-class-4.3` từ bản đang chạy và dùng gói nguồn này để thử trên staging riêng. KHÔNG kết nối hai môi trường thử nghiệm và thật với cùng database nếu không có kế hoạch.
3. Migration thêm cột `notices.deleted_at`, `notices.audience`, bảng `notice_targets` trong `init_db()` (DDL bổ sung, không xóa dữ liệu). Cần quyền DDL khi khởi động.
4. Kiểm thử: ngày/giờ Việt Nam trên iOS và Android; thông báo toàn lớp; thông báo riêng chỉ tới phụ huynh liên kết; tài khoản phụ huynh không được chọn không thể truy cập qua API hoặc đường dẫn tệp; xóa mềm và truy cập lại bị từ chối; kiểm tra các chức năng cũ, R2 và Web Push.
5. Nếu gặp lỗi, giữ bản sao lưu và quay lại image/commit cũ. Vì migration là bổ sung, rollback mã nguồn không cần xóa cột mới.

## Ghi chú
- Chưa có kiểm thử tích hợp PostgreSQL/Render/iPhone/Android trong môi trường của trường.
- Web Push chỉ hoạt động nếu VAPID đã cấu hình và phụ huynh đã đăng ký thiết bị.
- Thông báo riêng có nội dung cá nhân: không ghi thông tin nhạy cảm vào tiêu đề, tệp hay nội dung thông báo đẩy.
- Trước khi dùng dữ liệu học sinh thật, thay mọi khóa từng xuất hiện trong ảnh chụp và hoàn tất rà soát quyền truy cập.

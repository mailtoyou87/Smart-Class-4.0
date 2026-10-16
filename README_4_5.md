# Smart Class 4.5 – Chạm banner để làm mới dữ liệu

Bản phát triển dựa trên Smart Class 4.4.

- Chạm/click banner **🎓 Smart Class** để gọi lại API lấy dữ liệu hiện hành, không đăng xuất.
- Giữ lớp đang chọn, hỗ trợ phụ huynh, giáo viên và Admin.
- Có trạng thái đang cập nhật, thành công hoặc lỗi, ngăn nhấn liên tục.
- Hỗ trợ bàn phím Enter/Space; API GET dùng `cache: no-store` để lấy dữ liệu mới.
- Nâng phiên bản cache Service Worker để cập nhật JS mới.

## Triển khai an toàn

1. Sao lưu dữ liệu và mã nguồn đang chạy.
2. Đưa nội dung ZIP lên nhánh GitHub thử nghiệm, giữ cấu trúc thư mục.
3. Deploy vào dịch vụ Render staging, kiểm tra phiên đăng nhập không bị mất.
4. Mở 2 tài khoản trên 2 thiết bị: giáo viên đăng thông báo, phụ huynh chạm banner và xác nhận nhìn thấy; làm tương tự với phản hồi và đơn nghỉ học.
5. Kiểm tra tài khoản Admin và đổi lớp đang chọn.

**Lưu ý:** Đây là thao tác làm mới thủ công theo yêu cầu, không tự động chạy nền. Nội dung đang gõ dở trong form có thể mất nếu bấm banner; hoàn thành nhập trước khi làm mới. Chưa kiểm thử tích hợp Render/PostgreSQL hoặc điện thoại thật.

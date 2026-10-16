# Smart Class 4.4 – Phản hồi phụ huynh và đơn xin nghỉ học

## Tính năng mới

1. **Phụ huynh → Phản hồi:** chọn thông báo được gửi đến tài khoản, gửi nội dung riêng; giáo viên được phân công lớp hoặc Admin đọc và trả lời tại **Hộp thư phụ huynh**. Các cuộc hội thoại phân tách theo `(notice_id, parent_id)`, không công khai với phụ huynh khác. Giới hạn 2.000 ký tự và 5 tin/phút/người/thông báo.
2. **Phụ huynh → Đơn xin nghỉ học:** chọn học sinh đang liên kết, ngày nghỉ, buổi sáng/chiều/cả ngày, lý do (tối đa 1.000 ký tự), xác nhận và gửi. Theo dõi trạng thái và ý kiến giáo viên.
3. **Giáo viên/Admin → Duyệt đơn nghỉ học:** chỉ xem đơn thuộc lớp được phân quyền; đồng ý, yêu cầu bổ sung hoặc không đồng ý; ghi lý do và lưu người/thời gian xử lý. Không thể duyệt lại đơn đã xử lý.

## Cơ sở dữ liệu và an toàn

- `init_db()` tạo bổ sung hai bảng `notice_replies`, `absence_requests` và các index. Không xóa hoặc sửa bảng cũ. PostgreSQL cần quyền tạo bảng khi khởi động.
- Mọi API đều xác thực cookie và kiểm tra phân quyền trên máy chủ; các thao tác ghi yêu cầu header `X-Smart-Request: 1` và kiểm tra Origin.
- Phụ huynh chỉ gửi đơn cho học sinh có liên kết và chưa lưu trữ; chỉ xem đơn của chính mình; chỉ phản hồi thông báo thuộc danh sách người nhận.
- Giáo viên chỉ xử lý lớp được phân công. Admin được quản lý theo lớp.
- Dữ liệu lưu nhật ký audit. Xóa vĩnh viễn tài khoản có lịch sử đơn/phản hồi bị chặn để tránh phá hủy lịch sử.
- **Chưa có thông báo đẩy cho phản hồi và đơn xin nghỉ:** dữ liệu mới hiển thị khi tải lại giao diện. Tính năng push cũ của thông báo lớp vẫn được giữ.
- Khi giáo viên chọn `Cần bổ sung`, phụ huynh có thể xem lý do nhưng hiện chưa có thao tác sửa/nộp lại chính đơn đó; có thể tạo đơn mới sau khi nhà trường thống nhất quy trình.

## Hướng dẫn triển khai staging

1. Sao lưu PostgreSQL 4.3 và kiểm tra khả năng phục hồi. Không thay thế bản đang sử dụng khi chưa nghiệm thu.
2. Tạo nhánh `smart-class-4.4`, tải toàn bộ nguồn từ ZIP vào nhánh, dùng Render triển khai **staging riêng**. Không chia sẻ cùng database với production nếu chưa có kế hoạch.
3. Không đổi `SMART_SECRET`, `DATABASE_URL`, thông số R2 và VAPID nếu đã cấu hình đúng; tuyệt đối không commit khóa vào GitHub.
4. Kiểm tra nhật ký Render khi khởi động, bảo đảm migration tạo hai bảng mới thành công.
5. Kiểm thử với hai phụ huynh của hai học sinh khác nhau và một giáo viên: phụ huynh A không thể xem tin/đơn của B, giáo viên ngoài lớp không được xem/duyệt; phụ huynh A gửi phản hồi, giáo viên trả lời, A xem được trả lời; phụ huynh gửi đơn sáng/chiều/cả ngày, giáo viên duyệt và phụ huynh xem trạng thái.
6. Kiểm thử hồi quy: đăng nhập, tạo lớp, nhập CSV, liên kết học sinh, thông báo riêng, xác nhận đọc, tệp R2, xóa mềm, Web Push và giờ Việt Nam.

## Trạng thái xác nhận

Đã kiểm tra cú pháp Python và JavaScript, tính toàn vẹn ZIP. **Chưa có kiểm thử tích hợp với PostgreSQL/Render hoặc trên thiết bị thật**, do vậy đây là gói triển khai thử nghiệm, không phải bản đã nghiệm thu.

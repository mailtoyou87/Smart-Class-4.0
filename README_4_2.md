# Smart Class 4.2 — bản phát triển thử nghiệm

Nguồn: Smart Class 4.1. Đây là gói mã nguồn thử nghiệm, **không phải bản đã kiểm thử tích hợp** với PostgreSQL, Render, Web Push trên Android/iOS. Không triển khai trực tiếp lên dịch vụ đang dùng dữ liệu thật.

## Chức năng
- Bỏ banner BẢN THÍ ĐIỂM trên trang chủ. Việc ẩn banner không thay thế quy trình phê duyệt.
- Admin có thể xóa vĩnh viễn học sinh sau khi nhập đúng mã học sinh; xóa giáo viên/phụ huynh sau khi nhập đúng username. Các tài khoản có lịch sử thông báo hoặc còn phân công lớp được **chặn xóa** để không phá khóa ngoại, lịch sử xác nhận; có thể khóa tài khoản bằng chức năng sẵn có.
- Phụ huynh tự bật/tắt Web Push trên thiết bị. Giáo viên đăng thông báo mới: hệ thống gửi đến các thiết bị phụ huynh trong danh sách người nhận của lớp (đã đăng ký).
- Giáo viên xem người chưa đọc và nhấn nhắc; chỉ gửi cho người chưa đọc, giới hạn một lần gửi thành công trong 24 giờ cho mỗi phụ huynh/thông báo.

## Cấu hình bổ sung Render
- `VAPID_PUBLIC_KEY`: application server public key (base64url, không phải PEM).
- `VAPID_PRIVATE_KEY`: khóa bí mật VAPID dạng PEM được thư viện pywebpush hỗ trợ; nhập dạng giá trị bí mật của Render, không commit.
- `VAPID_SUBJECT`: `mailto:email-quan-tri-cua-truong@example.com` (thay bằng email thật).
- Giữ nguyên `DATABASE_URL`, `SMART_SECRET` và các biến R2. Không lưu bất kỳ khóa bí mật nào trong GitHub.

Tạo cặp khóa VAPID theo tài liệu `py-vapid`/`pywebpush`, bảo đảm public key khớp private key. Kiểm tra `GET /api/push/public-key` khi đã đăng nhập trả về `enabled:true`. Thư viện cần thêm: `pywebpush` (đã ghi trong requirements).

## Cách triển khai an toàn
1. Sao lưu PostgreSQL 4.0/4.1, kiểm tra có thể khôi phục.
2. Tạo nhánh Git `smart-class-4.2` từ commit đang hoạt động. Không đẩy thẳng vào nhánh Render tự động deploy.
3. Triển khai staging riêng với **database thử nghiệm riêng** (không trỏ staging mới vào DB sản xuất).
4. Các bảng mới được tạo bằng `CREATE TABLE IF NOT EXISTS` lúc ứng dụng khởi động: `push_subscriptions`, `notice_reminders`, `push_events`.
5. Đăng ký nhận thông báo trên Android Chrome PWA và iOS 16.4+ (cài vào Home Screen, bật quyền). Không thể đảm bảo push ngay lập tức hoặc khi tắt quyền, mất mạng.
6. Kiểm tra thông báo đến đúng lớp, không trùng cho một thiết bị; nhắc người chưa đọc; không nhắc người đã đọc; giới hạn 24 giờ; xóa tài khoản và kiểm tra dữ liệu liên quan.
7. Chỉ tạo Pull Request sau khi kiểm thử, rà soát bảo mật và phê duyệt.

## Giới hạn hiện tại
- Gửi Web Push đồng bộ trong yêu cầu đăng thông báo; với nhiều phụ huynh cần chuyển sang hàng đợi/background worker, cơ chế retry và kiểm soát timeout.
- Chức năng xóa tài khoản có lịch sử thông báo sẽ bị từ chối thay vì tự xóa lịch sử. Cần chính sách lưu giữ/xóa dữ liệu được nhà trường duyệt trước khi thiết kế xóa triệt để.
- Cần kiểm thử thực tế trên PostgreSQL, iOS, Android và kiểm tra bảo mật trước khi sử dụng dữ liệu thật.

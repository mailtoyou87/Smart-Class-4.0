# Smart Class 4.1 — PostgreSQL + private Cloudflare R2

Bản nâng cấp từ **Smart Class 4.0** (thí điểm). Giữ nguyên các luồng giáo viên/phụ huynh/admin, bổ sung:

1. Quản trị viên xóa mềm / khôi phục học sinh; không xóa lịch sử hay quan hệ trong DB.
2. Giáo viên xem từng phụ huynh đã đọc/chưa đọc và thời gian đọc theo danh sách người nhận chụp tại lúc đăng thông báo mới.
3. Đính kèm tối đa **5 tệp/thông báo**, mỗi tệp **8 MB**, chỉ JPG/JPEG/PNG/PDF/DOCX; lưu riêng tư trên Cloudflare R2; API kiểm tra quyền khi tải và xóa.
4. Admin xem/lọc/hủy liên kết phụ huynh–học sinh.
5. Hiện/ẩn mật khẩu ở đăng nhập, đổi mật khẩu, tạo/đặt lại tài khoản.

**Chưa triển khai**: thông báo đẩy PWA, kiểm tra virus tự động, xóa vĩnh viễn, sao lưu tự động R2, bộ giới hạn đăng nhập phân tán. Không coi đây là bản đã được kiểm định bảo mật để lưu dữ liệu thật.

## 1. Nâng cấp AN TOÀN trên Render từ 4.0

**Không tạo Blueprint mới, không đổi tên tài nguyên PostgreSQL.** Bản ZIP chứa `render.yaml` giữ nguyên `smart-class-v4-staging` và `smart-class-v4-staging-db`, nên dùng **cùng repository và Blueprint** hiện có. Nếu dùng repo/Blueprint khác, hãy triển khai với **database riêng** thay vì cùng quản lý một tài nguyên bởi hai Blueprint.

1. **Sao lưu PostgreSQL 4.0 trước khi sửa**: `pg_dump -Fc -f smartclass_before_41.dump "$DATABASE_URL"` từ máy quản trị có kết nối hợp lệ; xác minh `pg_restore -l smartclass_before_41.dump`. **Thử khôi phục vào DB riêng** và kiểm tra bản sao trước khi nâng cấp. Không đưa bản dump lên GitHub.
2. Xuất/ghi nhận số dòng `users`, `classes`, `students`, `parent_students`, `notices`, `notice_reads` trước nâng cấp; lưu bản mã nguồn 4.0 để có thể quay lại.
3. Tạo bucket R2 và token theo mục 2; thêm các biến R2 trong **Render > Web Service > Environment**. **Không ghi khóa trong GitHub hoặc `render.yaml`.**
4. Tải **nội dung** ZIP lên repository GitHub đang quản lý Smart Class 4.0, giữ `backend/`, `frontend/`, `render.yaml` ở thư mục gốc; kiểm tra `render.yaml` không tạo DB mới hay đổi service. Sync/deploy theo quy trình hiện tại.
5. Khi khởi động, `init_db()` thực hiện migration **cộng thêm, idempotent**: thêm `students.deleted_at`, bảng `notice_recipients`, `notice_attachments` và index. Không xóa bảng hoặc cột cũ. `CREATE TABLE IF NOT EXISTS` và `ADD COLUMN IF NOT EXISTS` giúp triển khai lặp lại an toàn hơn, **nhưng không thay thế sao lưu**.
6. Kiểm tra `/api/health`, số dòng và các chức năng cũ. Đăng thông báo **mới** để thử danh sách người nhận, upload/tải file, xóa mềm/khôi phục và liên kết phụ huynh. Kiểm thử bằng dữ liệu giả.
7. Khi lỗi, giữ DB, phục hồi mã nguồn 4.0 (các bảng/cột mới vẫn còn và không làm hỏng các truy vấn 4.0). Nếu cần phục hồi DB, chỉ `pg_restore` vào DB **độc lập**, không ghi đè trực tiếp DB đang dùng.

**Lưu ý:** Render gói Free không hỗ trợ `preDeployCommand`; bản này chạy các DDL cộng thêm khi khởi động. Khi vận hành thật nên dùng Alembic migrations có version và bước triển khai được kiểm soát. Dữ liệu 4.0 vẫn giữ nguyên.

## 2. Tạo Cloudflare R2 và thiết lập khóa

1. Đăng nhập https://dash.cloudflare.com → **R2 Object Storage** → **Create bucket**. Đặt tên ví dụ `smart-class-attachments-staging`. **Không bật Public Development URL hay public custom domain**.
2. Vào **R2 > Manage API Tokens** → tạo token có **Object Read & Write** và giới hạn **chỉ bucket vừa tạo**. Sao chép `Access Key ID` và `Secret Access Key` một lần; không chia sẻ qua chat hoặc GitHub.
3. Sao chép **Account ID** và xác định endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
4. Trong Render → `smart-class-v4-staging` → **Environment** thêm:

| Biến | Giá trị |
|---|---|
| `R2_ENDPOINT` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `R2_BUCKET` | `smart-class-attachments-staging` (tên bucket thật) |
| `R2_ACCESS_KEY_ID` | Access Key ID do Cloudflare cấp |
| `R2_SECRET_ACCESS_KEY` | Secret Access Key do Cloudflare cấp |

Giữ nguyên `DATABASE_URL`, `SMART_SECRET`, `SMART_HTTPS`, `SMART_ENV` hiện tại. **Không thay đổi `SMART_SECRET`** vì sẽ làm mất hiệu lực phiên đăng nhập hiện tại. Render tự khởi động lại khi cập nhật biến.

**Không cần cấu hình CORS trên R2**: browser tải tệp lên FastAPI cùng origin, FastAPI tải lên R2; tải xuống cũng qua API có xác thực. Tệp không public và không dùng URL R2 trực tiếp.

Tài liệu Cloudflare: https://developers.cloudflare.com/r2/get-started/s3/ và https://developers.cloudflare.com/r2/examples/aws/boto3/.

## 3. Thông báo cũ (4.0) và người đã đọc

Smart Class 4.0 không lưu danh sách người nhận lúc đăng; 4.1 **không thể biết chính xác ai chưa đọc thông báo cũ**. Đối với thông báo mới, danh sách người nhận được ghi vào `notice_recipients` ngay khi đăng, không tự đổi theo danh sách phụ huynh sau đó.

**Tùy chọn**, nếu muốn hiển thị danh sách **ước tính** cho thông báo cũ, sau khi sao lưu và kiểm tra SQL hãy chạy thủ công:

```bash
CONFIRM_LEGACY_BACKFILL=YES DATABASE_URL='...' python scripts/backfill_legacy_recipients.py
```

Lệnh lấy liên kết hiện tại theo lớp và người từng xác nhận; **không khôi phục được danh sách nhận lịch sử thực**. Không chạy tự động trong `render.yaml`.

## 4. Kịch bản nghiệm thu

- Tạo lớp và nhập học sinh mẫu → xóa mềm → học sinh ẩn khỏi danh sách lớp → khôi phục → xuất hiện trở lại.
- Admin xem danh sách liên kết, hủy liên kết → phụ huynh không còn thấy học sinh sau khi tải lại.
- Đăng thông báo mới với hai phụ huynh mẫu → một người xác nhận → giáo viên thấy **đúng tên** đã đọc/chưa đọc và thời gian.
- Đính kèm JPG, PNG, PDF, DOCX → phụ huynh đúng lớp tải được; người không có quyền bị API từ chối.
- Thử tệp giả dạng PDF/ảnh, `.exe`, >8 MB và tệp thứ 6 → bị từ chối.
- Kiểm tra con mắt ở các trường mật khẩu và thử lại **11 chức năng cũ**.
- Kiểm tra dữ liệu và file sau restart/redeploy. Sao lưu/khôi phục trên DB test độc lập.

## 5. Giới hạn quan trọng

- Không quét malware trong DOCX/PDF: người dùng chỉ nên tải tài liệu đáng tin cậy; trước vận hành thật cần tích hợp quét và quy trình kiểm duyệt nội dung.
- Xóa tệp trên R2 và xóa bản ghi DB không phải giao dịch phân tán; nếu một bước thất bại có thể cần đối soát thủ công.
- Hiển thị học sinh đang liên kết trong bảng người nhận là **trạng thái hiện tại**, không phải lịch sử quan hệ tại thời điểm đăng.
- 4.1 vẫn hiển thị thông báo lớp cho phụ huynh thuộc lớp theo hành vi 4.0; **không gửi nội dung nhạy cảm của một học sinh trong thông báo chung**.
- Chưa có push notification hoặc dashboard nhắc người chưa đọc; sẽ phát triển ở bản tiếp theo.
- Không nhập dữ liệu học sinh thật khi chưa có phê duyệt, kiểm thử bảo mật độc lập, sao lưu tự động/khôi phục được kiểm chứng và quy trình xử lý dữ liệu cá nhân.

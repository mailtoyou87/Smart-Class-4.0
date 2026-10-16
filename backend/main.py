import os, sqlite3, hashlib, hmac, secrets, datetime, time, threading, json, logging
from contextlib import contextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
import csv, io, uuid, mimetypes, zipfile, re
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import psycopg
from psycopg.rows import dict_row
from psycopg import errors as pg_errors

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get("SMART_DB", ROOT / "smart.db"))
SECRET = os.environ.get("SMART_SECRET", "")
if len(SECRET) < 32:
    raise RuntimeError("Set SMART_SECRET to a random value of at least 32 characters.")
signer = URLSafeTimedSerializer(SECRET, salt="smart-homeroom-v2")
app = FastAPI(title="Smart Class API v4.4", docs_url="/api/docs", openapi_url="/api/openapi.json")
# Same-origin UI/API; do not enable wildcard cross-origin credentials.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL (PostgreSQL) is required for Smart Class 4.0")
if os.environ.get("SMART_DEMO_SEED") == "YES" and os.environ.get("SMART_ENV") == "production":
    raise RuntimeError("Demo seeding is forbidden in production")

class CursorAdapter:
    def __init__(self, cur, lastrowid=None):
        self.cur, self.lastrowid = cur, lastrowid
    def fetchone(self): return self.cur.fetchone()
    def fetchall(self): return self.cur.fetchall()
    def __iter__(self): return iter(self.cur)
    def __getitem__(self, index): return self.cur[index]

class ConnectionAdapter:
    def __init__(self, conn): self.conn=conn
    def execute(self, sql, args=()):
        sql=sql.replace("?", "%s").replace("INSERT OR IGNORE INTO", "INSERT INTO")
        if sql.lstrip().upper().startswith("INSERT INTO") and "ON CONFLICT" not in sql.upper() and ("teacher_classes" in sql or "parent_students" in sql or "notice_reads" in sql):
            sql += " ON CONFLICT DO NOTHING"
        if "INSERT INTO users(" in sql or "INSERT INTO classes(" in sql or "INSERT INTO notices(" in sql or "INSERT INTO students(" in sql or "INSERT INTO notice_attachments(" in sql:
            sql += " RETURNING id"
            cur=self.conn.execute(sql,args)
            row=cur.fetchone()
            return CursorAdapter(cur, row['id'] if row else None)
        return CursorAdapter(self.conn.execute(sql,args))
    def executemany(self,sql,records):
        sql=sql.replace("?", "%s")
        with self.conn.cursor() as cur: cur.executemany(sql,records)

@contextmanager
def db():
    with psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=10) as conn:
        yield ConnectionAdapter(conn)

def init_db():
    with db() as c:
        for statement in [
            "CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','teacher','parent')), password_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, session_version INTEGER NOT NULL DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS classes(id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, school_year TEXT NOT NULL, UNIQUE(name,school_year))",
            "CREATE TABLE IF NOT EXISTS teacher_classes(teacher_id BIGINT NOT NULL REFERENCES users(id), class_id BIGINT NOT NULL REFERENCES classes(id), PRIMARY KEY(teacher_id,class_id))",
            "CREATE TABLE IF NOT EXISTS students(id BIGSERIAL PRIMARY KEY, class_id BIGINT NOT NULL REFERENCES classes(id), code TEXT UNIQUE NOT NULL, name TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS parent_students(parent_id BIGINT NOT NULL REFERENCES users(id), student_id BIGINT NOT NULL REFERENCES students(id), PRIMARY KEY(parent_id,student_id))",
            "CREATE TABLE IF NOT EXISTS notices(id BIGSERIAL PRIMARY KEY, class_id BIGINT NOT NULL REFERENCES classes(id), author_id BIGINT NOT NULL REFERENCES users(id), title TEXT NOT NULL, body TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
            "CREATE TABLE IF NOT EXISTS notice_reads(notice_id BIGINT NOT NULL REFERENCES notices(id) ON DELETE CASCADE, parent_id BIGINT NOT NULL REFERENCES users(id), read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(notice_id,parent_id))",
            "CREATE INDEX IF NOT EXISTS idx_students_class ON students(class_id)",
            "CREATE INDEX IF NOT EXISTS idx_notices_class ON notices(class_id)",
            "CREATE TABLE IF NOT EXISTS audit_log(id BIGSERIAL PRIMARY KEY, actor_id BIGINT, action TEXT NOT NULL, subject TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE students ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
            "CREATE TABLE IF NOT EXISTS notice_recipients(notice_id BIGINT NOT NULL REFERENCES notices(id) ON DELETE CASCADE, parent_id BIGINT NOT NULL REFERENCES users(id), PRIMARY KEY(notice_id,parent_id))",
            "CREATE TABLE IF NOT EXISTS notice_attachments(id BIGSERIAL PRIMARY KEY, notice_id BIGINT NOT NULL REFERENCES notices(id) ON DELETE CASCADE, object_key TEXT UNIQUE NOT NULL, filename TEXT NOT NULL, content_type TEXT NOT NULL, file_size INTEGER NOT NULL CHECK(file_size > 0), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
            "CREATE INDEX IF NOT EXISTS idx_notice_recipients_parent ON notice_recipients(parent_id)",
            "ALTER TABLE notices ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ",
            "ALTER TABLE notices ADD COLUMN IF NOT EXISTS audience TEXT NOT NULL DEFAULT 'class'",
            "CREATE TABLE IF NOT EXISTS notice_targets(notice_id BIGINT NOT NULL REFERENCES notices(id) ON DELETE CASCADE, student_id BIGINT NOT NULL REFERENCES students(id), PRIMARY KEY(notice_id,student_id))",
            "CREATE TABLE IF NOT EXISTS push_subscriptions(id BIGSERIAL PRIMARY KEY,parent_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,endpoint TEXT UNIQUE NOT NULL,subscription_json TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
            "CREATE INDEX IF NOT EXISTS idx_push_parent ON push_subscriptions(parent_id)",
            "CREATE TABLE IF NOT EXISTS notice_reminders(notice_id BIGINT NOT NULL REFERENCES notices(id) ON DELETE CASCADE,parent_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(notice_id,parent_id))",
            "CREATE TABLE IF NOT EXISTS push_events(id BIGSERIAL PRIMARY KEY,notice_id BIGINT REFERENCES notices(id) ON DELETE SET NULL,parent_id BIGINT REFERENCES users(id) ON DELETE SET NULL,kind TEXT NOT NULL,status TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
            "CREATE TABLE IF NOT EXISTS notice_replies(id BIGSERIAL PRIMARY KEY,notice_id BIGINT NOT NULL REFERENCES notices(id) ON DELETE CASCADE,parent_id BIGINT NOT NULL REFERENCES users(id),sender_id BIGINT NOT NULL REFERENCES users(id),body TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
            "CREATE INDEX IF NOT EXISTS idx_notice_replies_notice_parent ON notice_replies(notice_id,parent_id,created_at)",
            "CREATE TABLE IF NOT EXISTS absence_requests(id BIGSERIAL PRIMARY KEY,student_id BIGINT NOT NULL REFERENCES students(id),class_id BIGINT NOT NULL REFERENCES classes(id),parent_id BIGINT NOT NULL REFERENCES users(id),absence_date DATE NOT NULL,session TEXT NOT NULL CHECK(session IN ('morning','afternoon','full')),reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','needs_info','rejected')),teacher_note TEXT NOT NULL DEFAULT '',reviewer_id BIGINT REFERENCES users(id),reviewed_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())",
            "CREATE INDEX IF NOT EXISTS idx_absence_class_date ON absence_requests(class_id,absence_date DESC)",
            "CREATE INDEX IF NOT EXISTS idx_absence_parent ON absence_requests(parent_id,created_at DESC)",
        ]: c.execute(statement)
init_db()

def r2_client():
    import boto3
    endpoint=os.environ.get("R2_ENDPOINT", "").strip()
    bucket=os.environ.get("R2_BUCKET", "").strip()
    key=os.environ.get("R2_ACCESS_KEY_ID", "").strip()
    secret=os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
    if not all((endpoint,bucket,key,secret)):
        raise HTTPException(503,"Chưa cấu hình Cloudflare R2")
    if not endpoint.startswith("https://") or not re.fullmatch(r"https://[a-fA-F0-9]{32}\.r2\.cloudflarestorage\.com/?",endpoint):
        raise HTTPException(503,"R2_ENDPOINT không hợp lệ")
    return boto3.client("s3",endpoint_url=endpoint.rstrip("/"),aws_access_key_id=key,
                        aws_secret_access_key=secret,region_name="auto"),bucket

def audit(c, actor_id, action, subject=''):
    c.execute("INSERT INTO audit_log(actor_id,action,subject) VALUES(?,?,?)",(actor_id,action,str(subject)[:200]))

# Per-process login throttle; deploy with a single worker until a shared limiter is added.
_failed_logins={}
_login_lock=threading.Lock()
def check_login_throttle(request, username):
    key=(request.client.host if request.client else 'unknown', username.lower())
    now=time.monotonic()
    with _login_lock:
        count, start=_failed_logins.get(key,(0,now))
        if now-start>900: count,start=0,now
        if count>=8: raise HTTPException(429,"Quá nhiều lần đăng nhập sai. Vui lòng thử lại sau 15 phút")
    return key
def record_login_failure(key):
    now=time.monotonic()
    with _login_lock:
        count,start=_failed_logins.get(key,(0,now))
        if now-start>900: count,start=0,now
        _failed_logins[key]=(count+1,start)
def clear_login_failure(key):
    with _login_lock: _failed_logins.pop(key,None)

def hash_password(p):
    salt=secrets.token_bytes(16)
    key=hashlib.scrypt(p.encode(),salt=salt,n=16384,r=8,p=1)
    return salt.hex()+":"+key.hex()
def verify_password(p,stored):
    try:
        a,b=stored.split(":")
        actual=hashlib.scrypt(p.encode(),salt=bytes.fromhex(a),n=16384,r=8,p=1)
        return hmac.compare_digest(actual,bytes.fromhex(b))
    except (ValueError,TypeError): return False
def current_user(request: Request):
    token=request.cookies.get("sh_session")
    if not token: raise HTTPException(401,"Vui lòng đăng nhập")
    try: session=signer.loads(token,max_age=60*60*8)
    except (BadSignature,SignatureExpired): raise HTTPException(401,"Phiên đăng nhập hết hạn")
    if not isinstance(session,dict): raise HTTPException(401,"Vui lòng đăng nhập lại")
    uid=session.get("id")
    with db() as c:
        u=c.execute("SELECT id,username,name,role,session_version FROM users WHERE id=? AND active=1",(uid,)).fetchone()
    if u and u["session_version"]!=session.get("version"): raise HTTPException(401,"Phiên đăng nhập đã bị thu hồi")
    if not u: raise HTTPException(401,"Tài khoản không hợp lệ")
    return {k:u[k] for k in ("id","username","name","role")}
def csrf(request:Request):
    # SameSite=Lax and same-origin custom header for write endpoints.
    if request.headers.get("X-Smart-Request")!="1":
        raise HTTPException(403,"Thiếu tiêu đề bảo vệ yêu cầu")
    origin=request.headers.get("origin")
    if origin:
        from urllib.parse import urlparse
        a,b=urlparse(origin),urlparse(str(request.base_url))
        if (a.scheme,a.netloc)!=(b.scheme,b.netloc):
            raise HTTPException(403,"Nguồn yêu cầu không hợp lệ")
def classes_for(c,u):
    if u["role"]=="admin": return [r["id"] for r in c.execute("SELECT id FROM classes")]
    if u["role"]=="teacher":
        return [r["class_id"] for r in c.execute("SELECT class_id FROM teacher_classes WHERE teacher_id=?",(u["id"],))]
    return [r["class_id"] for r in c.execute("""
        SELECT DISTINCT s.class_id FROM students s JOIN parent_students ps ON ps.student_id=s.id
        WHERE ps.parent_id=? AND s.deleted_at IS NULL""",(u["id"],))]
def can_class(c,u,class_id):
    if class_id not in classes_for(c,u): raise HTTPException(403,"Không có quyền với lớp này")
class Login(BaseModel):
    username:str
    password:str
class NoticeIn(BaseModel):
    class_id:int
    title:str=Field(min_length=1,max_length=120)
    body:str=Field(min_length=1,max_length=3000)
    student_ids:list[int]=Field(default_factory=list,max_length=100)
@app.post("/api/login")
def login(payload:Login,response:Response,request:Request):
    csrf(request)
    key=check_login_throttle(request,payload.username)
    with db() as c:
        u=c.execute("SELECT * FROM users WHERE username=? AND active=1",(payload.username,)).fetchone()
    if not u or not verify_password(payload.password,u["password_hash"]):
        record_login_failure(key)
        raise HTTPException(401,"Sai tài khoản hoặc mật khẩu")
    clear_login_failure(key)
    response.set_cookie("sh_session",signer.dumps({"id":u["id"],"version":u["session_version"]}),max_age=28800,
                        httponly=True,secure=os.environ.get("SMART_HTTPS")=="1",
                        samesite="lax",path="/")
    return {"id":u["id"],"name":u["name"],"role":u["role"]}
@app.post("/api/logout")
def logout(response:Response,request:Request):
    csrf(request)
    response.delete_cookie("sh_session",path="/")
    return {"ok":True}
@app.get("/api/me")
def me(u=Depends(current_user)):return u
@app.get("/api/classes")
def classes(u=Depends(current_user)):
    with db() as c:
        ids=classes_for(c,u)
        return [dict(c.execute("SELECT * FROM classes WHERE id=?",(i,)).fetchone()) for i in ids]
@app.get("/api/students")
def students(class_id:int,u=Depends(current_user)):
    with db() as c:
        can_class(c,u,class_id)
        if u["role"]=="parent":
            rows=c.execute("""SELECT s.id,s.code,s.name,s.class_id FROM students s
            JOIN parent_students ps ON ps.student_id=s.id
            WHERE s.class_id=? AND ps.parent_id=? AND s.deleted_at IS NULL ORDER BY s.name""",(class_id,u["id"]))
        else:
            rows=c.execute("SELECT id,code,name,class_id FROM students WHERE class_id=? AND deleted_at IS NULL ORDER BY name",(class_id,))
        return [dict(r) for r in rows]
@app.get("/api/notices")
def notices(class_id:int,u=Depends(current_user)):
    with db() as c:
        can_class(c,u,class_id)
        # Parents may see only announcements explicitly addressed to them.
        sql="""SELECT n.id,n.class_id,n.title,n.body,n.created_at,n.audience,
            a.name AS author,
            EXISTS(SELECT 1 FROM notice_reads r WHERE r.notice_id=n.id AND r.parent_id=%s) AS is_read,
            (SELECT STRING_AGG(DISTINCT st.name, ', ' ORDER BY st.name)
             FROM notice_targets nt JOIN students st ON st.id=nt.student_id
             WHERE nt.notice_id=n.id AND (%s <> 'parent' OR EXISTS (SELECT 1 FROM parent_students ps WHERE ps.student_id=st.id AND ps.parent_id=%s))) AS target_names
            FROM notices n JOIN users a ON a.id=n.author_id
            WHERE n.class_id=%s AND n.deleted_at IS NULL"""
        args=[u["id"],u["role"],u["id"],class_id]
        if u["role"]=="parent":
            sql+=" AND EXISTS(SELECT 1 FROM notice_recipients nr WHERE nr.notice_id=n.id AND nr.parent_id=%s)"
            args.append(u["id"])
        sql+=" ORDER BY n.id DESC LIMIT 100"
        return [dict(r) for r in c.execute(sql,tuple(args))]

@app.post("/api/notices",status_code=201)
def create_notice(payload:NoticeIn,request:Request,u=Depends(current_user)):
    csrf(request)
    if u["role"] not in ("admin","teacher"):raise HTTPException(403,"Chỉ giáo viên và quản trị viên được gửi thông báo")
    ids=list(dict.fromkeys(payload.student_ids))
    with db() as c:
        can_class(c,u,payload.class_id)
        if ids:
            matched={r["id"] for r in c.execute("SELECT id FROM students WHERE class_id=%s AND deleted_at IS NULL AND id=ANY(%s)",(payload.class_id,ids))}
            if matched!=set(ids):raise HTTPException(400,"Danh sách học sinh nhận thông báo không hợp lệ")
            recipients=[r["parent_id"] for r in c.execute("""SELECT DISTINCT ps.parent_id FROM parent_students ps
                JOIN users p ON p.id=ps.parent_id AND p.active=1
                WHERE ps.student_id=ANY(%s)""",(ids,))]
            if not recipients:raise HTTPException(400,"Các học sinh đã chọn chưa liên kết với phụ huynh đang hoạt động")
        cur=c.execute("INSERT INTO notices(class_id,author_id,title,body,audience) VALUES(?,?,?,?,?)",
            (payload.class_id,u["id"],payload.title.strip(),payload.body.strip(),"selected" if ids else "class"))
        notice_id=cur.lastrowid
        if ids:
            c.executemany("INSERT INTO notice_targets(notice_id,student_id) VALUES(%s,%s)",[(notice_id,i) for i in ids])
            c.executemany("INSERT INTO notice_recipients(notice_id,parent_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",[(notice_id,i) for i in recipients])
        else:
            c.execute("""INSERT INTO notice_recipients(notice_id,parent_id)
                SELECT DISTINCT %s, ps.parent_id FROM students s
                JOIN parent_students ps ON ps.student_id=s.id
                JOIN users p ON p.id=ps.parent_id
                WHERE s.class_id=%s AND s.deleted_at IS NULL AND p.active=1
                ON CONFLICT DO NOTHING""",(notice_id,payload.class_id))
        audit(c,u["id"],"create_private_notice" if ids else "create_class_notice",str(notice_id))
    send_push_for_notice(notice_id,kind="new")
    return {"id":notice_id,"audience":"selected" if ids else "class"}

@app.delete("/api/notices/{notice_id}")
def delete_notice(notice_id:int,request:Request,u=Depends(current_user)):
    csrf(request)
    if u["role"] not in ("admin","teacher"):raise HTTPException(403,"Chỉ giáo viên và quản trị viên được xóa thông báo")
    with db() as c:
        n=c.execute("SELECT class_id,deleted_at FROM notices WHERE id=%s",(notice_id,)).fetchone()
        if not n or n["deleted_at"] is not None:raise HTTPException(404,"Không tìm thấy thông báo")
        can_class(c,u,n["class_id"])
        c.execute("UPDATE notices SET deleted_at=NOW() WHERE id=%s",(notice_id,))
        audit(c,u["id"],"archive_notice",str(notice_id))
    return {"ok":True,"message":"Đã ẩn thông báo khỏi phụ huynh và giáo viên"}

@app.post("/api/notices/{notice_id}/read")
def mark_read(notice_id:int,request:Request,u=Depends(current_user)):
    csrf(request)
    if u["role"]!="parent":raise HTTPException(403,"Chỉ phụ huynh xác nhận đã đọc")
    with db() as c:
        n=c.execute("SELECT class_id FROM notices WHERE id=? AND deleted_at IS NULL",(notice_id,)).fetchone()
        if not n:raise HTTPException(404,"Không có thông báo")
        can_class(c,u,n["class_id"])
        if not c.execute("SELECT 1 FROM notice_recipients WHERE notice_id=? AND parent_id=?",(notice_id,u["id"])).fetchone():
            raise HTTPException(403,"Không thuộc danh sách nhận thông báo")
        c.execute("INSERT OR IGNORE INTO notice_reads(notice_id,parent_id) VALUES(?,?)",(notice_id,u["id"]))
    return {"ok":True}
@app.get("/api/notices/{notice_id}/read-count")
def read_count(notice_id:int,u=Depends(current_user)):
    if u["role"]=="parent":raise HTTPException(403,"Không có quyền")
    with db() as c:
        n=c.execute("SELECT class_id FROM notices WHERE id=? AND deleted_at IS NULL",(notice_id,)).fetchone()
        if not n:raise HTTPException(404,"Không có thông báo")
        can_class(c,u,n["class_id"])
        count=c.execute("SELECT count(*) AS count FROM notice_reads r JOIN notice_recipients nr ON nr.notice_id=r.notice_id AND nr.parent_id=r.parent_id WHERE r.notice_id=?",(notice_id,)).fetchone()["count"]
    return {"count":count}

# Administrator workflows: demonstration-only, server-side authorization enforced.
def admin_only(u):
    if u["role"] != "admin": raise HTTPException(403,"Chỉ quản trị viên được thao tác")
class NewUser(BaseModel):
    username:str=Field(min_length=3,max_length=60,pattern=r"^[a-zA-Z0-9_.-]+$")
    name:str=Field(min_length=1,max_length=120)
    role:str
    password:str=Field(min_length=12,max_length=128)
class NewClass(BaseModel):
    name:str=Field(min_length=1,max_length=60)
    school_year:str=Field(min_length=4,max_length=20)
class AssignTeacher(BaseModel):
    teacher_id:int
    class_id:int
class LinkParent(BaseModel):
    parent_id:int
    student_id:int
class ImportStudents(BaseModel):
    class_id:int
    csv_text:str=Field(min_length=1,max_length=300000)
@app.get("/api/admin/users")
def list_users(u=Depends(current_user)):
    admin_only(u)
    with db() as c:
        return [dict(r) for r in c.execute("SELECT id,username,name,role,active FROM users ORDER BY id")]
@app.post("/api/admin/users",status_code=201)
def add_user(payload:NewUser,request:Request,u=Depends(current_user)):
    csrf(request);admin_only(u)
    if payload.role not in ("teacher","parent"):raise HTTPException(400,"Vai trò không hợp lệ")
    with db() as c:
        try:
            cur=c.execute("INSERT INTO users(username,name,role,password_hash) VALUES(?,?,?,?)",(payload.username,payload.name.strip(),payload.role,hash_password(payload.password)))
        except pg_errors.UniqueViolation:raise HTTPException(409,"Tên đăng nhập đã tồn tại")
        return {"id":cur.lastrowid}
@app.post("/api/admin/classes",status_code=201)
def add_class(payload:NewClass,request:Request,u=Depends(current_user)):
    csrf(request);admin_only(u)
    with db() as c:
        try:cur=c.execute("INSERT INTO classes(name,school_year) VALUES(?,?)",(payload.name.strip(),payload.school_year.strip()))
        except pg_errors.UniqueViolation:raise HTTPException(409,"Lớp đã tồn tại")
        return {"id":cur.lastrowid}
@app.post("/api/admin/assign-teacher")
def assign_teacher(payload:AssignTeacher,request:Request,u=Depends(current_user)):
    csrf(request);admin_only(u)
    with db() as c:
        teacher=c.execute("SELECT id FROM users WHERE id=? AND role='teacher'",(payload.teacher_id,)).fetchone()
        cl=c.execute("SELECT id FROM classes WHERE id=?",(payload.class_id,)).fetchone()
        if not teacher or not cl:raise HTTPException(400,"Giáo viên hoặc lớp không hợp lệ")
        c.execute("INSERT OR IGNORE INTO teacher_classes VALUES(?,?)",(payload.teacher_id,payload.class_id))
    return {"ok":True}
@app.post("/api/admin/link-parent")
def link_parent(payload:LinkParent,request:Request,u=Depends(current_user)):
    csrf(request);admin_only(u)
    with db() as c:
        parent=c.execute("SELECT id FROM users WHERE id=? AND role='parent'",(payload.parent_id,)).fetchone()
        student=c.execute("SELECT id FROM students WHERE id=?",(payload.student_id,)).fetchone()
        if not parent or not student:raise HTTPException(400,"Phụ huynh hoặc học sinh không hợp lệ")
        if c.execute("SELECT deleted_at FROM students WHERE id=?",(payload.student_id,)).fetchone()["deleted_at"] is not None:
            raise HTTPException(400,"Không thể liên kết học sinh đã xóa")
        c.execute("INSERT OR IGNORE INTO parent_students VALUES(?,?)",(payload.parent_id,payload.student_id))
    return {"ok":True}
@app.post("/api/admin/import-students")
def import_students(payload:ImportStudents,request:Request,u=Depends(current_user)):
    csrf(request);admin_only(u)
    with db() as c:
        if not c.execute("SELECT 1 FROM classes WHERE id=?",(payload.class_id,)).fetchone():raise HTTPException(404,"Không tìm thấy lớp")
        try:
            reader=csv.DictReader(io.StringIO(payload.csv_text.lstrip('\ufeff')))
            if not reader.fieldnames or not {'code','name'}.issubset(set(reader.fieldnames)):
                raise HTTPException(400,"CSV cần có cột code,name")
            records=[]; seen=set()
            for row in reader:
                code=(row.get('code') or '').strip();name=(row.get('name') or '').strip()
                if not code or not name or len(code)>40 or len(name)>120 or code in seen:
                    raise HTTPException(400,"Dữ liệu CSV thiếu, trùng mã hoặc quá dài")
                seen.add(code);records.append((payload.class_id,code,name))
                if len(records)>500:raise HTTPException(400,"Tối đa 500 học sinh mỗi lần")
            if not records:raise HTTPException(400,"Tệp CSV trống")
            c.executemany("INSERT INTO students(class_id,code,name) VALUES(?,?,?)",records)
        except UnicodeError:raise HTTPException(400,"Tệp cần mã hóa UTF-8")
        except pg_errors.UniqueViolation:raise HTTPException(409,"Có mã học sinh đã tồn tại; chưa nhập dữ liệu")
    return {"imported":len(records)}

class ChangePassword(BaseModel):
    current_password:str
    new_password:str=Field(min_length=12,max_length=128)

@app.post("/api/account/change-password")
def change_password(payload:ChangePassword, request:Request, response:Response, u=Depends(current_user)):
    csrf(request)
    if payload.current_password==payload.new_password:
        raise HTTPException(400,"Mật khẩu mới phải khác mật khẩu cũ")
    with db() as c:
        account=c.execute("SELECT password_hash FROM users WHERE id=?",(u["id"],)).fetchone()
        if not verify_password(payload.current_password,account["password_hash"]):
            raise HTTPException(400,"Mật khẩu hiện tại không đúng")
        c.execute("UPDATE users SET password_hash=?,session_version=session_version+1 WHERE id=?",(hash_password(payload.new_password),u["id"]))
        audit(c,u["id"],"change_password")
    response.delete_cookie("sh_session",path="/")
    return {"ok":True,"message":"Đã đổi mật khẩu; vui lòng đăng nhập lại"}

class ResetPassword(BaseModel):
    user_id:int
    new_password:str=Field(min_length=12,max_length=128)

@app.post("/api/admin/reset-password")
def reset_password(payload:ResetPassword, request:Request, u=Depends(current_user)):
    csrf(request);admin_only(u)
    with db() as c:
        target=c.execute("SELECT id,role FROM users WHERE id=?",(payload.user_id,)).fetchone()
        if not target or target["role"]=="admin":
            raise HTTPException(400,"Không thể đặt lại mật khẩu tài khoản này")
        c.execute("UPDATE users SET password_hash=?,session_version=session_version+1 WHERE id=?",(hash_password(payload.new_password),payload.user_id))
        audit(c,u["id"],"reset_password",payload.user_id)
    return {"ok":True}

class AccountStatus(BaseModel):
    user_id:int
    active:bool

@app.post("/api/admin/account-status")
def account_status(payload:AccountStatus,request:Request,u=Depends(current_user)):
    csrf(request);admin_only(u)
    with db() as c:
        target=c.execute("SELECT id,role FROM users WHERE id=?",(payload.user_id,)).fetchone()
        if not target or target["role"]=="admin":
            raise HTTPException(400,"Không thể thay đổi tài khoản này")
        c.execute("UPDATE users SET active=?,session_version=session_version+1 WHERE id=?",(int(payload.active),payload.user_id))
        audit(c,u["id"],"account_status",f"{payload.user_id}:{payload.active}")
    return {"ok":True}


# Smart Class 4.1 - reversible deletion, administrator relationship audit.
@app.delete("/api/admin/students/{student_id}")
def delete_student(student_id:int,request:Request,u=Depends(current_user)):
    csrf(request);admin_only(u)
    with db() as c:
        row=c.execute("SELECT id,deleted_at FROM students WHERE id=?",(student_id,)).fetchone()
        if not row:raise HTTPException(404,"Không tìm thấy học sinh")
        if row["deleted_at"] is not None:raise HTTPException(409,"Học sinh đã được lưu trữ")
        c.execute("UPDATE students SET deleted_at=NOW() WHERE id=?",(student_id,))
        audit(c,u["id"],"archive_student",student_id)
    return {"ok":True}

@app.post("/api/admin/students/{student_id}/restore")
def restore_student(student_id:int,request:Request,u=Depends(current_user)):
    csrf(request);admin_only(u)
    with db() as c:
        if not c.execute("SELECT 1 FROM students WHERE id=?",(student_id,)).fetchone():
            raise HTTPException(404,"Không tìm thấy học sinh")
        c.execute("UPDATE students SET deleted_at=NULL WHERE id=?",(student_id,))
        audit(c,u["id"],"restore_student",student_id)
    return {"ok":True}

@app.get("/api/admin/students")
def admin_students(class_id:int,u=Depends(current_user)):
    admin_only(u)
    with db() as c:
        return [dict(r) for r in c.execute("SELECT id,code,name,class_id,deleted_at FROM students WHERE class_id=? ORDER BY name",(class_id,))]

@app.get("/api/admin/parent-links")
def parent_links(class_id:int|None=None,u=Depends(current_user)):
    admin_only(u)
    with db() as c:
        sql="""SELECT ps.parent_id,ps.student_id,p.name AS parent_name,p.username AS parent_username,
            s.name AS student_name,s.code AS student_code,s.class_id,c.name AS class_name,
            s.deleted_at IS NOT NULL AS student_archived
            FROM parent_students ps JOIN users p ON p.id=ps.parent_id
            JOIN students s ON s.id=ps.student_id JOIN classes c ON c.id=s.class_id"""
        if class_id is not None:sql+=" WHERE s.class_id=%s"
        sql+=" ORDER BY c.name,s.name,p.name"
        return [dict(r) for r in c.execute(sql,(class_id,) if class_id is not None else ())]

@app.delete("/api/admin/parent-links/{parent_id}/{student_id}")
def unlink_parent(parent_id:int,student_id:int,request:Request,u=Depends(current_user)):
    csrf(request);admin_only(u)
    with db() as c:
        c.execute("DELETE FROM parent_students WHERE parent_id=? AND student_id=?",(parent_id,student_id))
        audit(c,u["id"],"unlink_parent",f"{parent_id}:{student_id}")
    return {"ok":True}

@app.get("/api/notices/{notice_id}/read-status")
def read_status(notice_id:int,u=Depends(current_user)):
    if u["role"]=="parent":raise HTTPException(403,"Không có quyền")
    with db() as c:
        n=c.execute("SELECT class_id FROM notices WHERE id=? AND deleted_at IS NULL",(notice_id,)).fetchone()
        if not n:raise HTTPException(404,"Không tìm thấy thông báo")
        can_class(c,u,n["class_id"])
        rows=c.execute("""SELECT p.id,p.name,p.username,r.read_at,
            STRING_AGG(DISTINCT s.name, ', ' ORDER BY s.name) AS student_names
            FROM notice_recipients nr JOIN users p ON p.id=nr.parent_id
            LEFT JOIN notice_reads r ON r.notice_id=nr.notice_id AND r.parent_id=nr.parent_id
            LEFT JOIN parent_students ps ON ps.parent_id=p.id
            LEFT JOIN students s ON s.id=ps.student_id AND s.class_id=%s
            WHERE nr.notice_id=%s GROUP BY p.id,p.name,p.username,r.read_at
            ORDER BY r.read_at NULLS FIRST,p.name""",(n["class_id"],notice_id))
        result=[dict(r) for r in rows]
        return {"total":len(result),"read":sum(r["read_at"] is not None for r in result),"parents":result}

# R2 bucket stays private; all upload/download requests are authorized by the API.
ALLOWED_EXT={".jpg":"image/jpeg",".jpeg":"image/jpeg",".png":"image/png",
             ".pdf":"application/pdf",
             ".docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAX_FILE=8*1024*1024

def valid_upload(filename,data):
    ext=Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:raise HTTPException(400,"Chỉ hỗ trợ JPG, PNG, PDF, DOCX")
    if not data or len(data)>MAX_FILE:raise HTTPException(413,"Tệp phải có dung lượng từ 1 byte đến 8 MB")
    ok={".jpg":lambda d:d.startswith(b"\xff\xd8\xff"),
        ".jpeg":lambda d:d.startswith(b"\xff\xd8\xff"),
        ".png":lambda d:d.startswith(b"\x89PNG\r\n\x1a\n"),
        ".pdf":lambda d:d.startswith(b"%PDF-"),
        ".docx":lambda d:zipfile.is_zipfile(io.BytesIO(d)) and
            "[Content_Types].xml" in zipfile.ZipFile(io.BytesIO(d)).namelist() and
            "word/document.xml" in zipfile.ZipFile(io.BytesIO(d)).namelist()}[ext](data)
    if not ok:raise HTTPException(400,"Nội dung tệp không đúng định dạng")
    return ALLOWED_EXT[ext]

@app.post("/api/notices/{notice_id}/attachments",status_code=201)
async def upload_attachment(notice_id:int,request:Request,file:UploadFile=File(...),u=Depends(current_user)):
    csrf(request)
    if u["role"] not in ("admin","teacher"):raise HTTPException(403,"Không có quyền")
    with db() as c:
        n=c.execute("SELECT class_id FROM notices WHERE id=? AND deleted_at IS NULL",(notice_id,)).fetchone()
        if not n:raise HTTPException(404,"Không tìm thấy thông báo")
        can_class(c,u,n["class_id"])
        if c.execute("SELECT COUNT(*) AS n FROM notice_attachments WHERE notice_id=?",(notice_id,)).fetchone()["n"]>=5:
            raise HTTPException(400,"Tối đa 5 tệp mỗi thông báo")
    filename=Path((file.filename or "").replace("\\","/")).name
    if not filename or len(filename)>180:raise HTTPException(400,"Tên tệp không hợp lệ")
    data=await file.read(MAX_FILE+1)
    content_type=valid_upload(filename,data)
    client,bucket=r2_client()
    key=f"smart-class/notices/{notice_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
    from botocore.exceptions import BotoCoreError,ClientError
    try:
        client.put_object(Bucket=bucket,Key=key,Body=data,ContentType=content_type)
    except (BotoCoreError,ClientError):raise HTTPException(502,"Không tải được tệp lên R2")
    try:
        with db() as c:
            cur=c.execute("INSERT INTO notice_attachments(notice_id,object_key,filename,content_type,file_size) VALUES(?,?,?,?,?)",
                          (notice_id,key,filename,content_type,len(data)))
            audit(c,u["id"],"upload_attachment",cur.lastrowid)
            return {"id":cur.lastrowid,"filename":filename}
    except Exception:
        try:client.delete_object(Bucket=bucket,Key=key)
        except Exception:pass
        raise

@app.get("/api/notices/{notice_id}/attachments")
def list_attachments(notice_id:int,u=Depends(current_user)):
    with db() as c:
        n=c.execute("SELECT class_id FROM notices WHERE id=? AND deleted_at IS NULL",(notice_id,)).fetchone()
        if not n:raise HTTPException(404,"Không tìm thấy thông báo")
        can_class(c,u,n["class_id"])
        if u["role"]=="parent" and not c.execute("SELECT 1 FROM notice_recipients WHERE notice_id=? AND parent_id=?",(notice_id,u["id"])).fetchone():
            raise HTTPException(403,"Không thuộc danh sách nhận thông báo")
        return [dict(r) for r in c.execute("SELECT id,filename,file_size,content_type FROM notice_attachments WHERE notice_id=? ORDER BY id",(notice_id,))]

@app.get("/api/attachments/{attachment_id}/download")
def download_attachment(attachment_id:int,u=Depends(current_user)):
    with db() as c:
        row=c.execute("""SELECT a.*,n.class_id,n.id AS notice_id FROM notice_attachments a
            JOIN notices n ON n.id=a.notice_id WHERE a.id=? AND n.deleted_at IS NULL""",(attachment_id,)).fetchone()
        if not row:raise HTTPException(404,"Không tìm thấy tệp")
        can_class(c,u,row["class_id"])
        if u["role"]=="parent" and not c.execute("SELECT 1 FROM notice_recipients WHERE notice_id=? AND parent_id=?",(row["notice_id"],u["id"])).fetchone():
            raise HTTPException(403,"Không có quyền tải tệp")
    client,bucket=r2_client()
    from botocore.exceptions import BotoCoreError,ClientError
    try:obj=client.get_object(Bucket=bucket,Key=row["object_key"])
    except (BotoCoreError,ClientError):raise HTTPException(502,"Không đọc được tệp từ R2")
    from urllib.parse import quote
    filename=row["filename"].replace('"','').replace('\r','').replace('\n','')
    return StreamingResponse(obj["Body"].iter_chunks(chunk_size=65536),media_type="application/octet-stream",
        headers={"Content-Disposition":f"attachment; filename*=UTF-8''{quote(filename)}",
                 "Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})

@app.delete("/api/attachments/{attachment_id}")
def delete_attachment(attachment_id:int,request:Request,u=Depends(current_user)):
    csrf(request)
    if u["role"] not in ("admin","teacher"):raise HTTPException(403,"Không có quyền")
    with db() as c:
        row=c.execute("""SELECT a.object_key,n.class_id FROM notice_attachments a
            JOIN notices n ON n.id=a.notice_id WHERE a.id=? AND n.deleted_at IS NULL AND n.deleted_at IS NULL""",(attachment_id,)).fetchone()
        if not row:raise HTTPException(404,"Không tìm thấy tệp")
        can_class(c,u,row["class_id"])
    client,bucket=r2_client()
    from botocore.exceptions import BotoCoreError,ClientError
    try:client.delete_object(Bucket=bucket,Key=row["object_key"])
    except (BotoCoreError,ClientError):raise HTTPException(502,"Không thể xóa tệp trên R2")
    with db() as c:
        c.execute("DELETE FROM notice_attachments WHERE id=?",(attachment_id,))
        audit(c,u["id"],"delete_attachment",attachment_id)
    return {"ok":True}


# Smart Class 4.2 — Web Push (only subscribed parent devices)
log=logging.getLogger("smartclass.push")
def vapid_ready():
    return bool(os.getenv("VAPID_PUBLIC_KEY") and os.getenv("VAPID_PRIVATE_KEY") and os.getenv("VAPID_SUBJECT"))

def push_one(subscription, title, body, url):
    from pywebpush import webpush, WebPushException
    try:
        webpush(subscription_info=json.loads(subscription["subscription_json"]),
                data=json.dumps({"title":title,"body":body,"url":url},ensure_ascii=False),
                vapid_private_key=os.environ["VAPID_PRIVATE_KEY"],
                vapid_claims={"sub":os.environ["VAPID_SUBJECT"]},ttl=86400,timeout=8)
        return "sent"
    except WebPushException as exc:
        status=getattr(getattr(exc,"response",None),"status_code",None)
        if status in (404,410):
            with db() as c: c.execute("DELETE FROM push_subscriptions WHERE id=?",(subscription["id"],))
            return "expired"
        log.warning("Push delivery failed: status=%s",status)
        return "failed"
    except Exception:
        log.exception("Push delivery failed")
        return "failed"

def send_push_for_notice(notice_id,kind="new",parent_ids=None):
    if not vapid_ready():
        log.warning("Web Push not configured: set VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT")
        return {"sent":0,"failed":0,"not_configured":True}
    with db() as c:
        n=c.execute("SELECT id,title,class_id,audience FROM notices WHERE id=? AND deleted_at IS NULL",(notice_id,)).fetchone()
        if not n:return {"sent":0,"failed":0}
        sql="""SELECT ps.id,ps.parent_id,ps.subscription_json FROM push_subscriptions ps
            JOIN notice_recipients nr ON nr.parent_id=ps.parent_id
            JOIN users u ON u.id=ps.parent_id AND u.active=1
            WHERE nr.notice_id=?"""
        args=[notice_id]
        if kind=="reminder":
            sql+=" AND NOT EXISTS (SELECT 1 FROM notice_reads r WHERE r.notice_id=nr.notice_id AND r.parent_id=nr.parent_id)"
        if parent_ids is not None:
            if not parent_ids:return {"sent":0,"failed":0}
            sql+=" AND ps.parent_id=ANY(%s)";args.append(parent_ids)
        subscriptions=list(c.execute(sql,tuple(args)))
    counts={"sent":0,"failed":0,"expired":0}
    for sub in subscriptions:
        status=push_one(sub,"Smart Class — Nhắc xem thông báo" if kind=="reminder" else "Smart Class — Thông báo mới",
                        "Quý phụ huynh có thông báo cần xem." if kind=="reminder" else ("Có thông báo riêng mới" if n.get("audience")=="selected" else n["title"]),
                        "/?notice="+str(notice_id))
        counts[status]+=1
        with db() as c:
            c.execute("INSERT INTO push_events(notice_id,parent_id,kind,status) VALUES(?,?,?,?)",(notice_id,sub["parent_id"],kind,status))
    return counts

class PushSubscription(BaseModel):
    endpoint:str=Field(min_length=10,max_length=2048)
    keys:dict
    expirationTime:float|None=None

@app.get("/api/push/public-key")
def push_public_key(u=Depends(current_user)):
    return {"enabled":vapid_ready(),"public_key":os.getenv("VAPID_PUBLIC_KEY","") if vapid_ready() else ""}

@app.post("/api/push/subscribe")
def push_subscribe(payload:PushSubscription,request:Request,u=Depends(current_user)):
    csrf(request)
    if u["role"]!="parent":raise HTTPException(403,"Chỉ phụ huynh đăng ký nhận thông báo")
    if not vapid_ready():raise HTTPException(503,"Chưa cấu hình Web Push")
    if not payload.endpoint.startswith("https://") or not isinstance(payload.keys.get("p256dh"),str) or not isinstance(payload.keys.get("auth"),str):
        raise HTTPException(400,"Đăng ký thiết bị không hợp lệ")
    obj=payload.model_dump(exclude_none=True)
    with db() as c:
        c.execute("""INSERT INTO push_subscriptions(parent_id,endpoint,subscription_json) VALUES(%s,%s,%s)
            ON CONFLICT(endpoint) DO UPDATE SET parent_id=EXCLUDED.parent_id,subscription_json=EXCLUDED.subscription_json""",
            (u["id"],payload.endpoint,json.dumps(obj)))
    return {"ok":True}

@app.post("/api/push/unsubscribe")
def push_unsubscribe(payload:PushSubscription,request:Request,u=Depends(current_user)):
    csrf(request)
    with db() as c:c.execute("DELETE FROM push_subscriptions WHERE endpoint=? AND parent_id=?",(payload.endpoint,u["id"]))
    return {"ok":True}

class ReminderIn(BaseModel):
    parent_ids:list[int]|None=None

@app.post("/api/notices/{notice_id}/remind")
def remind_unread(notice_id:int,payload:ReminderIn,request:Request,u=Depends(current_user)):
    csrf(request)
    if u["role"] not in ("admin","teacher"):raise HTTPException(403,"Không có quyền")
    with db() as c:
        n=c.execute("SELECT class_id FROM notices WHERE id=? AND deleted_at IS NULL",(notice_id,)).fetchone()
        if not n:raise HTTPException(404,"Không tìm thấy thông báo")
        can_class(c,u,n["class_id"])
        sql="""SELECT nr.parent_id FROM notice_recipients nr JOIN users us ON us.id=nr.parent_id AND us.active=1
          WHERE nr.notice_id=? AND NOT EXISTS(SELECT 1 FROM notice_reads r WHERE r.notice_id=nr.notice_id AND r.parent_id=nr.parent_id)
          AND NOT EXISTS(SELECT 1 FROM notice_reminders m WHERE m.notice_id=nr.notice_id AND m.parent_id=nr.parent_id AND m.sent_at>NOW()-INTERVAL '24 hours')"""
        args=[notice_id]
        if payload.parent_ids is not None:
            if not payload.parent_ids:return {"eligible":0,"sent":0}
            sql+=" AND nr.parent_id=ANY(%s)";args.append(payload.parent_ids)
        eligible=[r["parent_id"] for r in c.execute(sql,tuple(args))]
    if not vapid_ready():raise HTTPException(503,"Chưa cấu hình Web Push")
    if not eligible:return {"eligible":0,"sent":0}
    result=send_push_for_notice(notice_id,"reminder",eligible)
    # Count reminders only for users with a successful push, not those without subscriptions.
    with db() as c:
        sent_ids=[r["parent_id"] for r in c.execute("""SELECT DISTINCT parent_id FROM push_events WHERE notice_id=? AND kind='reminder' AND status='sent' AND created_at>NOW()-INTERVAL '2 minutes' AND parent_id=ANY(%s)""",(notice_id,eligible))]
        for pid in sent_ids:
            c.execute("""INSERT INTO notice_reminders(notice_id,parent_id,sent_at) VALUES(%s,%s,NOW())
                ON CONFLICT(notice_id,parent_id) DO UPDATE SET sent_at=EXCLUDED.sent_at""",(notice_id,pid))
        audit(c,u["id"],"remind_unread",f"notice:{notice_id};sent:{len(sent_ids)}")
    return {"eligible":len(eligible),"parents_notified":len(sent_ids),**result}

class DeleteConfirmation(BaseModel):
    confirm:str

def require_delete_confirmation(confirm,expected):
    if confirm!=expected:raise HTTPException(400,"Xác nhận xóa không khớp")

@app.post("/api/admin/students/{student_id}/purge")
def purge_student(student_id:int,payload:DeleteConfirmation,request:Request,u=Depends(current_user)):
    csrf(request);admin_only(u)
    with db() as c:
        row=c.execute("SELECT id,code FROM students WHERE id=?",(student_id,)).fetchone()
        if not row:raise HTTPException(404,"Không tìm thấy học sinh")
        require_delete_confirmation(payload.confirm,row["code"])
        c.execute("DELETE FROM parent_students WHERE student_id=?",(student_id,))
        c.execute("DELETE FROM students WHERE id=?",(student_id,))
        audit(c,u["id"],"purge_student",student_id)
    return {"ok":True}

@app.post("/api/admin/users/{user_id}/purge")
def purge_user(user_id:int,payload:DeleteConfirmation,request:Request,u=Depends(current_user)):
    csrf(request);admin_only(u)
    with db() as c:
        target=c.execute("SELECT id,username,role FROM users WHERE id=?",(user_id,)).fetchone()
        if not target:raise HTTPException(404,"Không tìm thấy tài khoản")
        if target["role"]=="admin":raise HTTPException(403,"Không được xóa tài khoản quản trị")
        require_delete_confirmation(payload.confirm,target["username"])
        if c.execute("SELECT 1 FROM notice_replies WHERE sender_id=? LIMIT 1",(user_id,)).fetchone() or c.execute("SELECT 1 FROM absence_requests WHERE reviewer_id=? OR parent_id=? LIMIT 1",(user_id,user_id)).fetchone():
            raise HTTPException(409,"Tài khoản có lịch sử phản hồi/đơn nghỉ học; hãy khóa thay vì xóa vĩnh viễn")
        if target["role"]=="teacher":
            # Historical notices remain attributed to the original author.
            if c.execute("SELECT 1 FROM notices WHERE author_id=? LIMIT 1",(user_id,)).fetchone():
                raise HTTPException(409,"Giáo viên có thông báo lịch sử: không thể xóa vĩnh viễn; hãy khóa tài khoản")
            if c.execute("SELECT 1 FROM teacher_classes WHERE teacher_id=? LIMIT 1",(user_id,)).fetchone():
                raise HTTPException(409,"Cần hủy phân công lớp trước khi xóa giáo viên")
        if target["role"]=="parent":
            if c.execute("SELECT 1 FROM notice_reads WHERE parent_id=? LIMIT 1",(user_id,)).fetchone() or c.execute("SELECT 1 FROM notice_recipients WHERE parent_id=? LIMIT 1",(user_id,)).fetchone():
                raise HTTPException(409,"Phụ huynh có lịch sử thông báo: không thể xóa vĩnh viễn mà không mất dấu vết; hãy khóa tài khoản")
            c.execute("DELETE FROM parent_students WHERE parent_id=?",(user_id,))
        c.execute("DELETE FROM push_subscriptions WHERE parent_id=?",(user_id,))
        c.execute("DELETE FROM users WHERE id=?",(user_id,))
        audit(c,u["id"],"purge_user",user_id)
    return {"ok":True}

# Smart Class 4.4: parent feedback and electronic absence requests.
class ReplyIn(BaseModel):
    body:str=Field(min_length=1,max_length=2000)
    parent_id:int|None=None


def reply_access(c,u,notice_id,parent_id=None):
    n=c.execute("SELECT id,class_id,deleted_at FROM notices WHERE id=?",(notice_id,)).fetchone()
    if not n or n['deleted_at'] is not None:raise HTTPException(404,"Thông báo không tồn tại")
    if u['role']=='parent':
        if parent_id is not None and parent_id!=u['id']:raise HTTPException(403,"Không có quyền xem phản hồi")
        if not c.execute("SELECT 1 FROM notice_recipients WHERE notice_id=? AND parent_id=?",(notice_id,u['id'])).fetchone():
            raise HTTPException(403,"Không thuộc danh sách nhận thông báo")
        return u['id']
    can_class(c,u,n['class_id'])
    if parent_id is None:raise HTTPException(400,"Cần chọn phụ huynh")
    if not c.execute("SELECT 1 FROM notice_recipients WHERE notice_id=? AND parent_id=?",(notice_id,parent_id)).fetchone():
        raise HTTPException(403,"Phụ huynh không thuộc danh sách nhận thông báo")
    return parent_id

@app.get('/api/replies/inbox')
def reply_inbox(class_id:int,u=Depends(current_user)):
    if u['role']=='parent':raise HTTPException(403,"Chỉ giáo viên và quản trị viên")
    with db() as c:
        can_class(c,u,class_id)
        rows=c.execute("""SELECT r.notice_id,r.parent_id,n.title,p.name AS parent_name,
            MAX(r.created_at) AS last_reply_at,COUNT(*) AS messages
            FROM notice_replies r JOIN notices n ON n.id=r.notice_id
            JOIN users p ON p.id=r.parent_id WHERE n.class_id=? AND n.deleted_at IS NULL
            GROUP BY r.notice_id,r.parent_id,n.title,p.name ORDER BY last_reply_at DESC LIMIT 100""",(class_id,)).fetchall()
        return [dict(x) for x in rows]

@app.get('/api/notices/{notice_id}/replies')
def get_replies(notice_id:int,parent_id:int|None=None,u=Depends(current_user)):
    with db() as c:
        pid=reply_access(c,u,notice_id,parent_id)
        rows=c.execute("""SELECT r.id,r.body,r.created_at,r.sender_id,s.name AS sender_name
            FROM notice_replies r JOIN users s ON s.id=r.sender_id
            WHERE r.notice_id=? AND r.parent_id=? ORDER BY r.id LIMIT 200""",(notice_id,pid)).fetchall()
        return [dict(x) for x in rows]

@app.post('/api/notices/{notice_id}/replies',status_code=201)
def post_reply(notice_id:int,payload:ReplyIn,request:Request,u=Depends(current_user)):
    csrf(request)
    body=payload.body.strip()
    if not body:raise HTTPException(422,"Nội dung không được để trống")
    with db() as c:
        pid=reply_access(c,u,notice_id,payload.parent_id)
        # Prevent a single user from flooding a conversation.
        recent=c.execute("""SELECT COUNT(*) AS n FROM notice_replies WHERE notice_id=? AND sender_id=?
            AND created_at > NOW()-INTERVAL '1 minute'""",(notice_id,u['id'])).fetchone()['n']
        if recent>=5:raise HTTPException(429,"Vui lòng đợi trước khi gửi thêm phản hồi")
        row=c.execute("INSERT INTO notice_replies(notice_id,parent_id,sender_id,body) VALUES(?,?,?,?) RETURNING id",(notice_id,pid,u['id'],body)).fetchone()
        audit(c,u['id'],'notice_reply',f'notice:{notice_id};parent:{pid}')
        return {'id':row['id'],'ok':True}

class AbsenceIn(BaseModel):
    student_id:int
    absence_date:datetime.date
    session:str
    reason:str=Field(min_length=1,max_length=1000)

@app.post('/api/absence-requests',status_code=201)
def create_absence(payload:AbsenceIn,request:Request,u=Depends(current_user)):
    csrf(request)
    if u['role']!='parent':raise HTTPException(403,"Chỉ phụ huynh được gửi đơn")
    if payload.session not in ('morning','afternoon','full'):raise HTTPException(422,"Buổi học không hợp lệ")
    reason=payload.reason.strip()
    if not reason:raise HTTPException(422,"Vui lòng nhập lý do")
    if payload.absence_date<datetime.date.today()-datetime.timedelta(days=30) or payload.absence_date>datetime.date.today()+datetime.timedelta(days=180):
        raise HTTPException(422,"Ngày nghỉ nằm ngoài phạm vi cho phép")
    with db() as c:
        student=c.execute("""SELECT s.id,s.class_id FROM students s JOIN parent_students ps ON ps.student_id=s.id
            WHERE s.id=? AND ps.parent_id=? AND s.deleted_at IS NULL""",(payload.student_id,u['id'])).fetchone()
        if not student:raise HTTPException(403,"Học sinh không liên kết với tài khoản")
        existing=c.execute("""SELECT id FROM absence_requests WHERE student_id=? AND absence_date=? AND session=?
            AND status IN ('pending','approved','needs_info') LIMIT 1""",(payload.student_id,payload.absence_date,payload.session)).fetchone()
        if existing:raise HTTPException(409,"Đã có đơn cho ngày và buổi học này")
        row=c.execute("""INSERT INTO absence_requests(student_id,class_id,parent_id,absence_date,session,reason)
            VALUES(?,?,?,?,?,?) RETURNING id""",(payload.student_id,student['class_id'],u['id'],payload.absence_date,payload.session,reason)).fetchone()
        audit(c,u['id'],'absence_created',row['id'])
        return {'id':row['id'],'status':'pending'}

@app.get('/api/absence-requests')
def list_absences(class_id:int,u=Depends(current_user)):
    with db() as c:
        can_class(c,u,class_id)
        sql="""SELECT a.id,a.student_id,a.absence_date,a.session,a.reason,a.status,a.teacher_note,
            a.created_at,a.reviewed_at,s.name AS student_name,p.name AS parent_name
            FROM absence_requests a JOIN students s ON s.id=a.student_id JOIN users p ON p.id=a.parent_id
            WHERE a.class_id=?"""
        args=[class_id]
        if u['role']=='parent':sql+=' AND a.parent_id=?';args.append(u['id'])
        sql+=' ORDER BY a.created_at DESC,a.id DESC LIMIT 200'
        return [dict(x) for x in c.execute(sql,tuple(args))]

class AbsenceReview(BaseModel):
    status:str
    teacher_note:str=Field(default='',max_length=1000)

@app.post('/api/absence-requests/{request_id}/review')
def review_absence(request_id:int,payload:AbsenceReview,request:Request,u=Depends(current_user)):
    csrf(request)
    if u['role'] not in ('teacher','admin'):raise HTTPException(403,"Chỉ giáo viên và quản trị viên")
    if payload.status not in ('approved','needs_info','rejected'):raise HTTPException(422,"Trạng thái không hợp lệ")
    with db() as c:
        row=c.execute("SELECT class_id,status FROM absence_requests WHERE id=? FOR UPDATE",(request_id,)).fetchone()
        if not row:raise HTTPException(404,"Không tìm thấy đơn")
        can_class(c,u,row['class_id'])
        if row['status']!='pending':raise HTTPException(409,"Đơn đã được xử lý")
        c.execute("""UPDATE absence_requests SET status=?,teacher_note=?,reviewer_id=?,reviewed_at=NOW() WHERE id=?""",
                  (payload.status,payload.teacher_note.strip(),u['id'],request_id))
        audit(c,u['id'],'absence_review',f'{request_id}:{payload.status}')
        return {'ok':True,'status':payload.status}

@app.get("/api/health")
def health():
    with db() as c: c.execute("SELECT 1")
    return {"status":"ok","database":"postgresql"}

WEB=ROOT.parent/"frontend"
app.mount("/assets",StaticFiles(directory=WEB),name="assets")
@app.get("/")
def home():return FileResponse(WEB/"index.html")

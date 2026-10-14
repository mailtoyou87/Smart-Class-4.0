import os, sqlite3, hashlib, hmac, secrets, datetime, time, threading
from contextlib import contextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import csv, io
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
app = FastAPI(title="Smart Class API v3", docs_url="/api/docs", openapi_url="/api/openapi.json")
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
        if "INSERT INTO users(" in sql or "INSERT INTO classes(" in sql or "INSERT INTO notices(" in sql or "INSERT INTO students(" in sql:
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
        ]: c.execute(statement)
init_db()

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
        WHERE ps.parent_id=?""",(u["id"],))]
def can_class(c,u,class_id):
    if class_id not in classes_for(c,u): raise HTTPException(403,"Không có quyền với lớp này")
class Login(BaseModel):
    username:str
    password:str
class NoticeIn(BaseModel):
    class_id:int
    title:str=Field(min_length=1,max_length=120)
    body:str=Field(min_length=1,max_length=3000)
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
            WHERE s.class_id=? AND ps.parent_id=? ORDER BY s.name""",(class_id,u["id"]))
        else:
            rows=c.execute("SELECT id,code,name,class_id FROM students WHERE class_id=? ORDER BY name",(class_id,))
        return [dict(r) for r in rows]
@app.get("/api/notices")
def notices(class_id:int,u=Depends(current_user)):
    with db() as c:
        can_class(c,u,class_id)
        rows=c.execute("""SELECT n.id,n.class_id,n.title,n.body,n.created_at,
            a.name AS author,
            EXISTS(SELECT 1 FROM notice_reads r WHERE r.notice_id=n.id AND r.parent_id=?) AS is_read
            FROM notices n JOIN users a ON a.id=n.author_id WHERE n.class_id=?
            ORDER BY n.id DESC LIMIT 100""",(u["id"],class_id))
        return [dict(r) for r in rows]
@app.post("/api/notices",status_code=201)
def create_notice(payload:NoticeIn,request:Request,u=Depends(current_user)):
    csrf(request)
    if u["role"] not in ("admin","teacher"):raise HTTPException(403,"Chỉ giáo viên được gửi thông báo")
    with db() as c:
        can_class(c,u,payload.class_id)
        cur=c.execute("INSERT INTO notices(class_id,author_id,title,body) VALUES(?,?,?,?)",
            (payload.class_id,u["id"],payload.title.strip(),payload.body.strip()))
        return {"id":cur.lastrowid}
@app.post("/api/notices/{notice_id}/read")
def mark_read(notice_id:int,request:Request,u=Depends(current_user)):
    csrf(request)
    if u["role"]!="parent":raise HTTPException(403,"Chỉ phụ huynh xác nhận đã đọc")
    with db() as c:
        n=c.execute("SELECT class_id FROM notices WHERE id=?",(notice_id,)).fetchone()
        if not n:raise HTTPException(404,"Không có thông báo")
        can_class(c,u,n["class_id"])
        c.execute("INSERT OR IGNORE INTO notice_reads(notice_id,parent_id) VALUES(?,?)",(notice_id,u["id"]))
    return {"ok":True}
@app.get("/api/notices/{notice_id}/read-count")
def read_count(notice_id:int,u=Depends(current_user)):
    if u["role"]=="parent":raise HTTPException(403,"Không có quyền")
    with db() as c:
        n=c.execute("SELECT class_id FROM notices WHERE id=?",(notice_id,)).fetchone()
        if not n:raise HTTPException(404,"Không có thông báo")
        can_class(c,u,n["class_id"])
        count=c.execute("SELECT count(*) AS count FROM notice_reads WHERE notice_id=?",(notice_id,)).fetchone()["count"]
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

@app.get("/api/health")
def health():
    with db() as c: c.execute("SELECT 1")
    return {"status":"ok","database":"postgresql"}

WEB=ROOT.parent/"frontend"
app.mount("/assets",StaticFiles(directory=WEB),name="assets")
@app.get("/")
def home():return FileResponse(WEB/"index.html")

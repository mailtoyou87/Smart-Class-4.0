"""Only use with fictional demo records; do not run on a production database."""
from main import db,hash_password
import os
if os.environ.get("SMART_ENV")=="production":
    raise SystemExit("Cannot seed demo data in production")
if os.environ.get("SMART_DEMO_SEED")!="YES":
    raise SystemExit("Set SMART_DEMO_SEED=YES to create fictional demo accounts.")
with db() as c:
    if c.execute("SELECT count(*) AS count FROM users").fetchone()["count"]:
        raise SystemExit("Database already contains accounts. Refusing to seed.")
    users=[
      ("admin","Quản trị mẫu","admin","DemoAdmin!2026"),
      ("gv_a","Giáo viên lớp 10A1","teacher","DemoTeacher!2026"),
      ("gv_b","Giáo viên lớp 10A2","teacher","DemoTeacher!2026"),
      ("ph_a","Phụ huynh mẫu A","parent","DemoParent!2026"),
      ("ph_b","Phụ huynh mẫu B","parent","DemoParent!2026")]
    for username,name,role,pw in users:
        c.execute("INSERT INTO users(username,name,role,password_hash) VALUES(?,?,?,?)",
                  (username,name,role,hash_password(pw)))
    c.executemany("INSERT INTO classes(name,school_year) VALUES(?,?)",
                  [("10A1","2026-2027"),("10A2","2026-2027")])
    c.executemany("INSERT INTO teacher_classes VALUES(?,?)",[(2,1),(3,2)])
    c.executemany("INSERT INTO students(class_id,code,name) VALUES(?,?,?)",
                  [(1,"HS001","Học sinh mẫu Một"),(1,"HS002","Học sinh mẫu Hai"),(2,"HS003","Học sinh mẫu Ba")])
    c.executemany("INSERT INTO parent_students VALUES(?,?)",[(4,1),(5,3)])
print("Demo created. Passwords are in README; never use them for real accounts.")

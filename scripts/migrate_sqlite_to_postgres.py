"""One-time offline migration into an EMPTY PostgreSQL database. Run only after backup.
Usage: python scripts/migrate_sqlite_to_postgres.py /path/to/smart.db
Requires DATABASE_URL, SMART_SECRET. Do NOT run against a seeded database.
"""
import os,sys,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
if len(sys.argv)!=2: raise SystemExit('Usage: python scripts/migrate_sqlite_to_postgres.py smart.db')
if os.environ.get('SMART_DEMO_SEED')=='YES': raise SystemExit('Disable SMART_DEMO_SEED before migration')
from main import db
source=sqlite3.connect(sys.argv[1]);source.row_factory=sqlite3.Row
order=['users','classes','teacher_classes','students','parent_students','notices','notice_reads']
with db() as dst:
    if dst.execute('SELECT COUNT(*) AS n FROM users').fetchone()['n']:
        raise SystemExit('Target DB is not empty. Migration stopped.')
    for table in order:
        rows=[dict(x) for x in source.execute('SELECT * FROM '+table)]
        if not rows: continue
        keys=list(rows[0]);cols=','.join(keys);holders=','.join(['?']*len(keys))
        # use raw psycopg to preserve primary keys, avoiding RETURNING adaptation
        for row in rows:
            dst.conn.execute('INSERT INTO '+table+' ('+cols+') VALUES ('+','.join(['%s']*len(keys))+')',tuple(row[k] for k in keys))
        print(table,len(rows))
    for table in ['users','classes','students','notices']:
        dst.conn.execute("SELECT setval(pg_get_serial_sequence(%s,'id'), COALESCE((SELECT MAX(id) FROM "+table+"),1), (SELECT COUNT(*)>0 FROM "+table+"))",(table,))
print('Migration completed. Verify counts and permissions before switching traffic.')

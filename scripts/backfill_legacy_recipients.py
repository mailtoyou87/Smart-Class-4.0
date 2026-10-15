"""Opt-in approximation for legacy notices: current class links + known read receipts.
Does not reconstruct historical intended recipients. Back up database first.
"""
import os, psycopg
if os.environ.get('CONFIRM_LEGACY_BACKFILL') != 'YES':
    raise SystemExit('Set CONFIRM_LEGACY_BACKFILL=YES after backup and review.')
url=os.environ['DATABASE_URL']
with psycopg.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute('''INSERT INTO notice_recipients(notice_id,parent_id)
            SELECT DISTINCT n.id, ps.parent_id FROM notices n
            JOIN students s ON s.class_id=n.class_id
            JOIN parent_students ps ON ps.student_id=s.id
            JOIN users u ON u.id=ps.parent_id WHERE u.role='parent'
            ON CONFLICT DO NOTHING''')
        estimated=cur.rowcount
        cur.execute('''INSERT INTO notice_recipients(notice_id,parent_id)
            SELECT r.notice_id,r.parent_id FROM notice_reads r
            ON CONFLICT DO NOTHING''')
        observed=cur.rowcount
print(f'Legacy approximation added: {estimated} current class links; {observed} historical reads.')

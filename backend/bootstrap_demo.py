"""Initialize schema, and optional fictional demo data for staging only."""
import os
from main import db
if os.environ.get('SMART_DEMO_SEED') == 'YES':
    if os.environ.get('SMART_ENV') == 'production':
        raise SystemExit('Demo seeding prohibited in production')
    with db() as c:
        exists=c.execute('SELECT COUNT(*) AS count FROM users').fetchone()['count']
    if not exists:
        import seed_demo

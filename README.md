# Smart Class 4.0 — staging pilot (2–5 classes)

## What is included
- Existing teacher/parent/admin workflows from v3.1: login, classes, student CSV import (`code,name`), teacher assignment, parent linking, class notices, read receipts and counts.
- PostgreSQL with persistent relational tables; account password change, admin reset/deactivate/reactivate, signed sessions invalidated on password change/reset, basic per-process login throttling, admin audit entries for account changes, and health endpoint.
- Render Blueprint to create **new staging web service** and a **new staging Postgres database**. It does not replace the v3.1 URL.
- Backup shell example and one-time SQLite migration utility.

## Deploy on Render — staging only
1. Keep the existing Smart Class 3.1 repository/service and database untouched. Make a NEW GitHub repository (`smart-class-v4-staging`) and upload the **contents** of this ZIP to its root (so `render.yaml`, `backend/`, `frontend/` are at root).
2. Render > New > Blueprint > connect new repo > review service `smart-class-v4-staging` and DB `smart-class-v4-staging-db` > apply. Render Blueprint uses `DATABASE_URL` linked to Postgres and a generated `SMART_SECRET`.
3. Confirm web service Live and `/api/health` returns `{"status":"ok","database":"postgresql"}`.
4. Use fictional demo accounts seeded on an empty staging database: `admin` / `DemoAdmin!2026`; `gv_a` / `DemoTeacher!2026`; `ph_a` / `DemoParent!2026`. **Immediately change passwords if staging is publicly accessible.** Never use real student data in this demo.
5. Re-test all 11 scenarios, password change, admin reset/deactivation and data persistence after redeploy.

## IMPORTANT: free Postgres and backups
Render Free Postgres is **not** an appropriate durable store for real student records: Free databases have lifecycle/availability limitations, and Render does **not** provide managed backups or recovery for Free databases. Choose a supported paid DB with recovery plus independent encrypted `pg_dump` backups before any real-data pilot. See https://render.com/docs/postgresql-backups and https://render.com/docs/postgresql.

To back up (from a trusted admin computer with `pg_dump` installed):
`DATABASE_URL='EXTERNAL_POSTGRES_URL' bash scripts/backup_postgres.sh`
Never commit `.dump` files, DB URLs, or `.env` to GitHub. Verify restore to an **isolated** test database using `pg_restore` before production.

## Data migration from v3.1
**Not automatic.** v3.1 uses SQLite on a potentially ephemeral Render filesystem. Export the SQLite DB only if it is still available, make an offline copy, then migrate into a **new empty** PostgreSQL DB with `SMART_DEMO_SEED` disabled:
`DATABASE_URL='...' SMART_SECRET='at-least-32-chars' python scripts/migrate_sqlite_to_postgres.py /path/to/smart.db`
The migration preserves password hashes and IDs but **invalidates existing signed login cookies** if the secret changes. Use separate staging database and verify user counts, class memberships, notices and read receipts before cutover. Never attempt migration against a seeded database.

## Known limits / security acceptance gates
- **Not production-ready**: login throttle is in-memory per worker, not a shared store; no self-service verified recovery or mandatory first-login password change; no independent external security audit; no automated scheduled backups or proven disaster recovery.
- Admin can reset only teacher/parent passwords; account changes are audited but not all mutations.
- Staging seeds public demo credentials only on empty DB. For production set `SMART_ENV=production`, `SMART_DEMO_SEED=NO`, provision admin through a secured one-time setup process, and remove all public demo accounts.
- Test access control with both UI and direct API requests. Configure TLS, school approval, privacy notices, data minimization, retention, and incident procedures before real data.
- This release retains v3.1's behavior that **notices are visible to all parents linked to the class**; individual student records are scoped to linked parents. Do not publish private student data in class-wide notices.

## Local development
Requires PostgreSQL and Python 3.11. Set `DATABASE_URL`, `SMART_SECRET` (32+ characters), and `SMART_HTTPS=0` for localhost. `cd backend && uvicorn main:app --reload`. Run optional demo seed with `SMART_DEMO_SEED=YES python seed_demo.py` against an empty database.

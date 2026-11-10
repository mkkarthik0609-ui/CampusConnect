# End-to-end tests (Playwright)

Runs against a throw-away local stack — never production.

```bash
# 1. scratch PostgreSQL (superuser, e.g. a temp cluster on :54329) and an empty database
createdb -h 127.0.0.1 -p 54329 -U postgres cc_e2e
# 2. build the SPA, start the API with a bootstrap admin (TEST credentials) serving frontend/dist on :8765
cd frontend && npm run build && cd ..
DATABASE_URL=postgresql://postgres@127.0.0.1:54329/cc_e2e DATABASE_URL_POOLED= APP_ENV=development \
  SECRET_KEY=e2e-secret-key-e2e-secret-key-0123456789 BOOTSTRAP_ADMIN=1 ADMIN_NAME="E2E Owner" \
  ADMIN_EMAIL=mkkarthik0609@gmail.com ADMIN_PASSWORD='E2e#Admin0wner1' ENABLE_SCHEDULER=0 \
  python -m uvicorn api.main:app --port 8765
# 3. seed users, run the suite
DATABASE_URL=postgresql://postgres@127.0.0.1:54329/cc_e2e DATABASE_URL_POOLED= python scripts/e2e_seed.py
cd frontend && npx playwright test
```

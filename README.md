# Banwee API

REST API for Banwee — premium organic products from Africa. Built with FastAPI, PostgreSQL, and Stripe.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.111 + Uvicorn |
| Database | SQLite (dev) / PostgreSQL (prod) with Alembic migrations |
| Auth | JWT (python-jose) + bcrypt/argon2 + OAuth (Google, Facebook) |
| Payments | Stripe |
| Email | Brevo (SendinBlue) |
| Background Jobs | asyncio scheduler (subscriptions, promocodes) |
| Documents | WeasyPrint (PDF invoices), Jinja2 |

---

## Project Structure

```
backend/
├── api/              # Route handlers (auth, catalog, commerce, admin, system)
├── models/           # SQLAlchemy ORM models
├── schemas/          # Pydantic request/response schemas
├── core/             # Config, DB, logging, exceptions, utils, background jobs
├── alembic/          # Database migrations
├── main.py           # App entry point
├── start-app.sh      # Startup script (dev / prod)
├── .env.dev          # Development environment variables
└── .env.prod         # Production environment variables
```

---

## Local Setup

**1. Create and activate a virtual environment**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure environment**

```bash
cp .env.dev.example .env.dev   # then fill in your secrets
```

See [Environment Variables](#environment-variables) for details.

**4. Database Setup**

The app supports **SQLite** (development) and **PostgreSQL** (production):

### Development (SQLite) - Auto Setup
```bash
# .env.dev - Uses SQLite by default
DATABASE_URL=sqlite:///./banwee.db

# Tables auto-create on first run - no migrations needed
uvicorn main:app --reload
```

### Production (PostgreSQL) - Manual Setup
```bash
# .env.prod - Use PostgreSQL
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Run migrations manually
alembic upgrade head

# Start app
uvicorn main:app
```

---

## Running the App

The `start-app.sh` script handles both modes. Run it from inside the `backend/` directory.

```bash
cd backend
chmod +x start-app.sh
```

### Development

```bash
./start-app.sh dev
```

- Loads `.env.dev`
- Uvicorn with hot reload and debug logging
- CORS open to `localhost:5173` / `localhost:3000`

### Production

```bash
./start-app.sh prod
```

- Loads `.env.prod`
- Gunicorn + UvicornWorker, 4 workers by default
- Override workers: `WORKERS=8 ./start-app.sh prod`

> Host and port are read from `BACKEND_URL` in the env file.

---

## API

All routes are versioned under `/v1`.

| Module | Prefix | Description |
|---|---|---|
| Auth | `/v1/auth` | Register, login, refresh, logout, password change |
| OAuth | `/v1/auth/oauth` | Google & Facebook login |
| Users | `/v1/users` | Profile, addresses |
| Products | `/v1/products` | Catalog, search, reviews, inventory, wishlist |
| Categories | `/v1/categories` | Category tree |
| Cart | `/v1/cart` | Cart management |
| Orders | `/v1/orders` | Order lifecycle |
| Payments | `/v1/payments` | Stripe payment methods & intents |
| Subscriptions | `/v1/subscriptions` | Recurring orders, auto-renewal |
| Promocodes | `/v1/promocodes` | Discount codes |
| Shipping | `/v1/shipping` | Methods, rates, tracking |
| Tax | `/v1/tax` | Tax rate management |
| Refunds | `/v1/refunds` | Refund requests |
| Webhooks | `/v1/webhooks` | Stripe webhook handler |
| Admin | `/v1/admin` | Admin operations & analytics |
| System | `/v1/health` | Health check, contact messages |

**Interactive docs** (available when the server is running):

- Swagger UI → `{BACKEND_URL}/docs`
- ReDoc → `{BACKEND_URL}/redoc`

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ENVIRONMENT` | ✅ | `dev` or `production` |
| `BACKEND_URL` | ✅ | Base URL of this API (e.g. `http://localhost:8000`) |
| `FRONTEND_URL` | ✅ | Frontend origin for CORS |
| `BACKEND_CORS_ORIGINS` | — | Comma-separated allowed origins (defaults per env) |
| `POSTGRES_DB_URL` | ✅ | Full PostgreSQL connection URL |
| `SECRET_KEY` | ✅ | JWT signing key (min 32 chars in dev, 64 in prod) |
| `ALGORITHM` | — | JWT algorithm, default `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | — | Default `1440` (24h) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | — | Default `7` |
| `STRIPE_SECRET_KEY` | ✅ | `sk_test_...` (dev) / `sk_live_...` (prod) |
| `STRIPE_WEBHOOK_SECRET` | ✅ | Stripe webhook signing secret |
| `BREVO_API_KEY` | ✅ | Brevo (SendinBlue) API key |
| `BREVO_FROM_EMAIL` | — | Sender address, default `Banwee <noreply@banwee.com>` |
| `GOOGLE_CLIENT_ID` | — | OAuth — Google |
| `GOOGLE_CLIENT_SECRET` | — | OAuth — Google |
| `FACEBOOK_APP_ID` | — | OAuth — Facebook |
| `FACEBOOK_APP_SECRET` | — | OAuth — Facebook |
| `ADMIN_USER_ID` | — | UUID of the admin user |

Generate a secure `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Database Migrations

> **Note:** Migrations are **required** for PostgreSQL (production) but **not needed** for SQLite (development). SQLite tables auto-create on startup.

### First time / fresh setup (PostgreSQL only)

```bash
alembic upgrade head
```

### After changing a model (add column, alter type, new table, etc.)

1. Edit your SQLAlchemy model in `models/`
2. Generate a migration — Alembic diffs your models against the DB:

```bash
alembic revision --autogenerate -m "add phone to users"
```

3. Review the generated file in `alembic/versions/` — autogenerate isn't perfect, always check it.

4. Apply it:

```bash
alembic upgrade head
```

### Other useful commands

```bash
# Roll back one migration
alembic downgrade -1

# Roll back to a specific revision
alembic downgrade <revision_id>

# Check what's applied
alembic current

# See full history
alembic history --verbose

# Show pending (unapplied) migrations
alembic history -r current:head
```

### Writing a manual migration

If autogenerate misses something (e.g. renaming a column, custom SQL, data migrations):

```bash
alembic revision -m "backfill order totals"
```

Then edit the generated file manually:

```python
def upgrade():
    op.execute("UPDATE orders SET total = subtotal + tax WHERE total IS NULL")

def downgrade():
    pass
```

---

## Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=. --cov-report=html

# Single file
pytest tests/path/to/test_file.py -v
```

---

## Health Check

```bash
curl {BACKEND_URL}/v1/health
```

```json
{ "status": "healthy" }
```

---

## Notes

- Never commit `.env.dev` or `.env.prod` — they are gitignored.
- In production, inject secrets via your CI/CD or hosting platform's secret store.
- Subscription renewals and promocode scheduling run automatically via the asyncio scheduler on startup.

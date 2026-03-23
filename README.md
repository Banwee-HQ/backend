# Banwee Backend - FastAPI Server

Complete guide for running and managing the Banwee backend server and ARQ worker.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Running the Backend](#running-the-backend)
- [Running the ARQ Worker](#running-the-arq-worker)
- [Environment Configuration](#environment-configuration)
- [Database Management](#database-management)
- [API Documentation](#api-documentation)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Banwee backend is built with FastAPI and provides:

- **24 API Routers** - Complete REST API for e-commerce operations
- **Async Operations** - Full async/await support for high performance
- **Background Jobs** - ARQ worker for scheduled tasks
- **Smart Features** - AI recommendations, auto-scheduling
- **Security** - JWT auth, password hashing, CORS protection
- **Caching** - Redis for improved performance
- **Testing** - 80%+ test coverage

### Key Components

- **FastAPI Server** - Main API server (port 8000)
- **ARQ Worker** - Background task processor (required)
- **PostgreSQL** - Database (Neon cloud)
- **Redis** - Cache (Upstash cloud)

---

## Prerequisites

### Required Software

- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **pip** - Python package manager (included with Python)
- **Git** - Version control

### Cloud Services (Pre-configured)

- ✅ **Neon PostgreSQL** - Database URL in `.env`
- ✅ **Upstash Redis** - Cache URL in `.env`

### Optional Services

- **Stripe** - Payment processing (optional for development)
- **Mailgun** - Email notifications (optional for development)

---

## Quick Start

### One-Command Setup

```bash
# From project root
./start-app.sh
```

This starts both the backend server and ARQ worker.

### Manual Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
python init_db.py

# Start backend server
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Running the Backend

### Development Mode (with auto-reload)

```bash
cd backend
source .venv/bin/activate
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Features:**
- ✅ Auto-reload on code changes
- ✅ Detailed error messages
- ✅ Debug mode enabled
- ✅ CORS configured for localhost

**Access:**
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Production Mode

```bash
cd backend
source .venv/bin/activate

# Using Uvicorn (single worker)
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Using Gunicorn (multiple workers - recommended)
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

**Production Configuration:**
- Multiple workers for better performance
- No auto-reload
- Production error handling
- Strict CORS origins
- Rate limiting enabled

### Server Options

| Option | Description | Example |
|--------|-------------|---------|
| `--host` | Bind address | `0.0.0.0` (all interfaces) |
| `--port` | Port number | `8000` |
| `--reload` | Auto-reload on changes | Development only |
| `--workers` | Number of worker processes | `4` (production) |
| `--log-level` | Logging level | `info`, `debug`, `warning` |

### Checking Server Status

```bash
# Check if server is running
curl http://localhost:8000/

# Expected response:
{
  "service": "Banwee API",
  "status": "Running",
  "version": "1.0.0"
}

# Check health endpoint
curl http://localhost:8000/v1/health

# Expected response:
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected"
}
```

---

## Running the ARQ Worker

### What is the ARQ Worker?

The ARQ worker is a **required** background task processor that handles:

1. **Subscription Renewals** - Daily at 2:00 AM UTC
   - Processes recurring subscription orders
   - Handles payment processing
   - Sends renewal notifications
   - Updates subscription status

2. **Promocode Auto-Scheduling** - Daily at 12:00 AM (midnight) UTC
   - Activates promocodes when `valid_from` date is reached
   - Deactivates promocodes when `valid_until` date is passed
   - Deactivates promocodes when usage limit is reached

3. **Background Email Sending** - As needed
   - Order confirmations
   - Shipping notifications
   - Password reset emails
   - Subscription updates

4. **Inventory Synchronization** - Periodic
   - Stock level updates
   - Low stock alerts

### Starting the ARQ Worker

#### Method 1: Using the Startup Script (Recommended)

```bash
cd backend
source .venv/bin/activate
python start_arq_worker.py
```

**Output:**
```
Starting ARQ worker...
Worker started successfully
Listening for tasks...
```

#### Method 2: Direct ARQ Command

```bash
cd backend
source .venv/bin/activate
arq core.arq_worker.WorkerSettings
```

#### Method 3: Using the Shell Script

```bash
cd backend
./start_arq_worker.sh
```

### ARQ Worker Configuration

The worker is configured in `backend/core/arq_worker.py`:

```python
# Subscription renewal - Daily at 2 AM UTC
cron(
    process_subscription_renewals_task,
    hour=2,
    minute=0,
    run_at_startup=False,
    unique=True,
    timeout=600  # 10 minutes
)

# Promocode scheduling - Daily at midnight UTC
cron(
    update_promocode_statuses_task,
    hour=0,
    minute=0,
    run_at_startup=False,
    unique=True,
    timeout=300  # 5 minutes
)
```

### Monitoring the ARQ Worker

#### Check Worker Status

```bash
# View worker logs
tail -f logs/arq_worker.log

# View error logs
tail -f logs/arq_worker_error.log

# Check if worker is running
ps aux | grep arq
```

#### Worker Logs

The worker logs all activities:

```
[2026-02-13 02:00:00] Starting subscription renewal task
[2026-02-13 02:00:01] Processing 15 subscriptions due for renewal
[2026-02-13 02:00:05] Successfully renewed 14 subscriptions
[2026-02-13 02:00:05] Failed to renew 1 subscription (payment failed)
[2026-02-13 02:00:05] Subscription renewal task completed
```

### Production Deployment

#### Using Supervisor (Recommended)

Create `/etc/supervisor/conf.d/banwee-arq.conf`:

```ini
[program:banwee-arq]
command=/path/to/backend/.venv/bin/python start_arq_worker.py
directory=/path/to/backend
user=www-data
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/path/to/backend/logs/arq_worker.log
stderr_logfile=/path/to/backend/logs/arq_worker_error.log
```

Start the worker:

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start banwee-arq
```

#### Using systemd

Create `/etc/systemd/system/banwee-arq.service`:

```ini
[Unit]
Description=Banwee ARQ Worker
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/backend
Environment="PATH=/path/to/backend/.venv/bin"
ExecStart=/path/to/backend/.venv/bin/python start_arq_worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Start the worker:

```bash
sudo systemctl daemon-reload
sudo systemctl enable banwee-arq
sudo systemctl start banwee-arq
sudo systemctl status banwee-arq
```

#### Using Docker

```dockerfile
# In docker-compose.yml
services:
  arq-worker:
    build: ./backend
    command: python start_arq_worker.py
    environment:
      - POSTGRES_DB_URL=${POSTGRES_DB_URL}
      - REDIS_URL=${REDIS_URL}
    depends_on:
      - backend
    restart: always
```

### Troubleshooting ARQ Worker

#### Worker Not Starting

```bash
# Check Python version
python --version  # Should be 3.11+

# Check dependencies
pip list | grep arq

# Reinstall dependencies
pip install -r requirements.txt

# Check Redis connection
python -c "import redis; r=redis.from_url('your-redis-url'); r.ping()"
```

#### Tasks Not Running

```bash
# Check worker logs
tail -f logs/arq_worker.log

# Verify cron schedule
python -c "from core.arq_worker import WorkerSettings; print(WorkerSettings.cron_jobs)"

# Manually trigger task (for testing)
python -c "
from core.arq_worker import enqueue_subscription_renewal
import asyncio
asyncio.run(enqueue_subscription_renewal())
"
```

#### High Memory Usage

```bash
# Monitor worker memory
ps aux | grep arq

# Restart worker
sudo supervisorctl restart banwee-arq

# Or with systemd
sudo systemctl restart banwee-arq
```

---

## Environment Configuration

### Required Environment Variables

Create `backend/.env` from `backend/.env.example`:

```env
# Database (Required)
POSTGRES_DB_URL=postgresql+asyncpg://user:pass@host:5432/db

# Redis (Required)
REDIS_URL=rediss://default:***@upstash.io:6379

# Security (Required)
SECRET_KEY=your-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Application
ENVIRONMENT=local
DEBUG=true
FRONTEND_URL=http://localhost:5173
BACKEND_CORS_ORIGINS=http://localhost:5173
```

### Optional Environment Variables

```env
# Stripe (for payments)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Mailgun (for emails)
MAILGUN_API_KEY=your-api-key
MAILGUN_DOMAIN=your-domain.com
MAILGUN_FROM_EMAIL=noreply@your-domain.com

# OAuth (optional)
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
FACEBOOK_APP_ID=your-app-id
FACEBOOK_APP_SECRET=your-app-secret
```

### Generating SECRET_KEY

```bash
# Using OpenSSL
openssl rand -hex 32

# Using Python
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Database Management

### Initialize Database

```bash
cd backend
source .venv/bin/activate
python init_db.py
```

This will:
1. Create all database tables
2. Seed initial data (admin user, categories, products)
3. Set up indexes and constraints

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current version
alembic current

# View migration history
alembic history
```

### Database Backup

```bash
# Backup database (if using local PostgreSQL)
pg_dump -U username -d banwee_db > backup.sql

# Restore database
psql -U username -d banwee_db < backup.sql
```

---

## API Documentation

### Interactive Documentation

Once the server is running:

- **Swagger UI**: http://localhost:8000/docs
  - Interactive API testing
  - Request/response examples
  - Authentication testing

- **ReDoc**: http://localhost:8000/redoc
  - Clean, readable documentation
  - Detailed schemas
  - Code examples

### API Endpoints Overview

| Category | Endpoints | Description |
|----------|-----------|-------------|
| **Auth** | `/v1/auth/*` | Login, register, password reset |
| **Users** | `/v1/users/*` | User profile, addresses |
| **Products** | `/v1/products/*` | Product catalog, search, recommendations |
| **Cart** | `/v1/cart/*` | Shopping cart operations |
| **Orders** | `/v1/orders/*` | Order management, tracking |
| **Payments** | `/v1/payments/*` | Payment processing, methods |
| **Subscriptions** | `/v1/subscriptions/*` | Subscription management |
| **Promocodes** | `/v1/promocodes/*` | Promo code operations |
| **Admin** | `/v1/admin/*` | Admin operations, analytics |
| **Wishlist** | `/v1/wishlist/*` | Wishlist management |
| **Reviews** | `/v1/reviews/*` | Product reviews |
| **Inventory** | `/v1/inventory/*` | Stock management |
| **Shipping** | `/v1/shipping/*` | Shipping methods, tracking |
| **Analytics** | `/v1/analytics/*` | Sales analytics, reports |
| **Webhooks** | `/v1/webhooks/*` | External webhooks (Stripe) |

### Testing API Endpoints

```bash
# Health check
curl http://localhost:8000/v1/health

# Login
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@banwee.com","password":"admin123"}'

# Get products
curl http://localhost:8000/v1/products?page=1&limit=10

# Get product recommendations
curl http://localhost:8000/v1/products/{product_id}/recommendations?limit=4
```

---

## Testing

### Running Tests

```bash
cd backend
source .venv/bin/activate

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/unit/test_auth_service.py

# Run specific test
pytest tests/unit/test_auth_service.py::test_login

# Run with verbose output
pytest -v

# Run and stop on first failure
pytest -x
```

### Test Categories

```bash
# Unit tests
pytest tests/unit/

# Integration tests
pytest tests/integration/

# API tests
pytest tests/api/

# Service tests
pytest tests/services/
```

### Test Coverage

View coverage report:

```bash
pytest --cov=. --cov-report=html
open htmlcov/index.html  # On macOS
# Or navigate to htmlcov/index.html in browser
```

Current coverage: **80%+**

---

## Troubleshooting

### Common Issues

#### 1. Server Won't Start

```bash
# Check if port is in use
lsof -i :8000

# Kill process using port
kill -9 <PID>

# Check Python version
python --version  # Should be 3.11+

# Reinstall dependencies
pip install -r requirements.txt
```

#### 2. Database Connection Error

```bash
# Check database URL in .env
cat .env | grep POSTGRES_DB_URL

# Test database connection
python -c "
from sqlalchemy import create_engine
engine = create_engine('your-db-url')
conn = engine.connect()
print('Connected!')
"
```

#### 3. Redis Connection Error

```bash
# Check Redis URL in .env
cat .env | grep REDIS_URL

# Test Redis connection
python -c "
import redis
r = redis.from_url('your-redis-url')
r.ping()
print('Connected!')
"
```

#### 4. Import Errors

```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt

# Check Python path
python -c "import sys; print(sys.path)"
```

#### 5. ARQ Worker Not Processing Tasks

```bash
# Check worker is running
ps aux | grep arq

# Check worker logs
tail -f logs/arq_worker.log

# Restart worker
# If using supervisor:
sudo supervisorctl restart banwee-arq

# If using systemd:
sudo systemctl restart banwee-arq
```

### Logs

```bash
# Application logs
tail -f logs/banwee.log

# Error logs
tail -f logs/banwee_error.log

# ARQ worker logs
tail -f logs/arq_worker.log

# Service-specific logs
tail -f logs/services.orders.log
tail -f logs/services.products.log
```

### Performance Issues

```bash
# Check database query performance
# Enable SQL logging in .env
SQLALCHEMY_ECHO=true

# Monitor Redis cache
redis-cli --stat

# Check memory usage
ps aux | grep python

# Profile application
python -m cProfile -o profile.stats main.py
```

---

## Additional Resources

- **[Main README](../README.md)** - Project overview
- **[Subscription Flow](SUBSCRIPTION_FLOW.md)** - Subscription system details
- **[API Cleanup](../API_CLEANUP_SUMMARY.md)** - API documentation
- **[Smart Recommendations](../SMART_RECOMMENDATIONS_COMPLETE.md)** - Recommendation engine

---

## Support

- **Issues**: [GitHub Issues](https://github.com/Oahse/banweemvp/issues)
- **Email**: support@banwee.com

---

<div align="center">
  <p>Made with ❤️ by the Banwee Team</p>
</div>

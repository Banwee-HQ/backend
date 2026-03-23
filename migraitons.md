# 🧱 Database & Alembic Workflow (Detailed)

## 0️⃣ Reset Alembic version tracking (NO DB CHANGES)

```bash
alembic stamp base
```

**What it does**

* Marks the DB as having **no migrations applied**
* Does **NOT** create or drop tables

**When to use**

* DB was manually cleared
* Alembic history is out of sync
* Fresh dev reset

⚠️ Never use alone to “reset” data — it only affects Alembic metadata.

---

## 1️⃣ Create initial migration (schema baseline)

```bash
alembic revision --autogenerate -m "initial schema"
```

**What it does**

* Compares SQLAlchemy models ↔ database
* Generates `op.create_table(...)` calls

**Important**

* Review the migration file
* Fix custom types (UUID / GUID / enums)
* Ensure indexes & constraints are correct

🚫 Never trust autogenerate blindly.

---

## 2️⃣ Apply migrations (build schema)

```bash
alembic upgrade head
```

**What it does**

* Runs all migrations up to the latest
* Creates tables
* Updates `alembic_version`

**Verify**

```bash
alembic current
```

---

## 3️⃣ Undo the LAST migration

```bash
alembic downgrade -1
```

**What it does**

* Runs `downgrade()` of the most recent revision
* Reverts only that change

**Use case**

* Migration mistake
* Schema rollback in dev

⚠️ Requires a valid `downgrade()` function.

---

## 4️⃣ Seed the database

```bash
python init_db.py --seed
```

**What it should do**

* Insert reference / test data
* Be **idempotent** (safe to run multiple times)
* Never create tables

**Best practice**

* Seed AFTER migrations
* Guard against duplicates

---

## 5️⃣ FULL RESET: Clear all data & tables (DEV ONLY)

### PostgreSQL

```sql
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
```

### Then reset Alembic & rebuild

```bash
alembic stamp base
alembic upgrade head
```

**What this gives you**

* Empty DB
* Fresh schema
* Clean Alembic history

🔥 This is the **recommended dev reset flow**.

---

## 🔁 Typical Daily Dev Workflow

```bash
# change models
alembic revision --autogenerate -m "describe change"
alembic upgrade head
python init_db.py --seed
```

---

## 🔐 Safety Checklist (DO THIS EVERY TIME)

```bash
alembic current
alembic history
```

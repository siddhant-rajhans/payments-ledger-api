# Payments Ledger API

![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Tests: 17 passing](https://img.shields.io/badge/tests-17%20passing-brightgreen)
![License: MIT](https://img.shields.io/badge/license-MIT-blue)

Double-entry payments ledger API in FastAPI and Postgres. Every transfer writes balanced debit and credit journal entries in a single serializable transaction. Idempotency keys on `POST /transfers` guarantee that a retried request returns the first result and never moves money twice. Row-level locks ordered by account ID prevent both deadlocks and negative balances under concurrent load. Reversals create new offsetting entries rather than mutating history, preserving a complete audit trail.

## Measured Results

Benchmarked on AMD Ryzen 5 3550H (4C/8T), 2 GB RAM, embedded Postgres via pgserver. Reproduce with `make bench` or `python scripts/run_benchmark.py` against a running instance.

| Metric | Value |
|--------|-------|
| Throughput (32 concurrent) | **97.7 transfers/s** |
| Latency p50 | **264 ms** |
| Latency p95 | **746 ms** |
| Latency p99 | **1,010 ms** |
| Balance drift after 1,000 concurrent transfers | **0** |
| Duplicate charges under 100 idempotent retries | **0** |
| Concurrent overdraft violations (20 parallel, 1,000-cent budget) | **0** (exactly 10/20 succeeded) |
| Global debit/credit balance | **Verified equal** |
| Test suite | **17/17 passing** |

## Architecture

```
                          ┌─────────┐
                          │ Client  │
                          └────┬────┘
                               │
                     POST /transfers
                   Idempotency-Key: ...
                               │
                               ▼
┌─────────────────────────────────────────────────┐
│                  FastAPI Gateway                 │
│                                                 │
│  ┌───────────────────┐   ┌───────────────────┐  │
│  │  Idempotency Key  │   │   Balance Check   │  │
│  │     Lookup        │   │   + Row Locks     │  │
│  │                   │   │  ORDER BY acct id │  │
│  │  Key exists?      │   │                   │  │
│  │  ├─ yes: return   │   │  Sufficient?      │  │
│  │  │   cached 201   │   │  ├─ no:  422      │  │
│  │  └─ no: continue  │   │  └─ yes: continue │  │
│  └─────────┬─────────┘   └─────────┬─────────┘  │
│            │                       │             │
│            └───────────┬───────────┘             │
│                        ▼                         │
│         ┌────────────────────────────┐           │
│         │   Double-Entry Write       │           │
│         │                            │           │
│         │   1. INSERT transfer       │           │
│         │   2. INSERT debit entry    │           │
│         │   3. INSERT credit entry   │           │
│         │                            │           │
│         │   (single SERIALIZABLE txn)│           │
│         └────────────┬───────────────┘           │
│                      │                           │
└──────────────────────┼───────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│                   PostgreSQL                     │
│                                                  │
│  ┌──────────┐  ┌─────────────────┐  ┌─────────┐ │
│  │ accounts │◄─┤ journal_entries ├─►│transfers│ │
│  └──────────┘  └─────────────────┘  └─────────┘ │
│                                                  │
│  Balance = SUM(credits) - SUM(debits)            │
│  Reconciliation: global debit == global credit   │
└──────────────────────────────────────────────────┘
```

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/accounts` | Create account (optionally allow overdraft) |
| GET | `/accounts/{id}` | Get account with computed balance |
| GET | `/accounts/{id}/entries` | List journal entries for account |
| POST | `/transfers` | Create transfer (Idempotency-Key header) |
| GET | `/transfers/{id}` | Get transfer with journal entries |
| POST | `/transfers/{id}/reverse` | Reverse a transfer (new offsetting entries) |
| GET | `/reconciliation` | Recompute all balances and verify global balance |
| GET | `/health` | Database connectivity check |

<details>
<summary><strong>Design Decisions</strong></summary>

### Integer arithmetic for money

Amounts are stored as `BIGINT` cents, never floats. This eliminates rounding errors that compound across thousands of transactions, which is the same reason Stripe and every payment processor uses integer-cent representation.

### Ordered row locks for deadlock prevention

Both accounts are locked with `SELECT ... FOR UPDATE` sorted by UUID. Without ordering, two concurrent transfers A->B and B->A can deadlock. Sorting guarantees a consistent lock acquisition order across all transactions.

### Idempotency keys in the database, not a cache

Keys are stored with a UNIQUE constraint on the transfers table. A Redis TTL cache would lose keys on restart, allowing duplicate charges during recovery. The database constraint is durable and survives restarts.

### Reversals as new entries, never mutations

Reversing a transfer creates a new transfer with inverted debit/credit entries. The original entries are never modified or deleted. This preserves a complete, tamper-evident audit trail where every state change is traceable.

### Balance recomputed from the journal on every read

`GET /accounts/{id}` computes balance as `SUM(credits) - SUM(debits)` rather than caching it in a mutable column. This eliminates write-write races on a balance column and makes the reconciliation endpoint a simple `SUM` comparison rather than a reconciliation against a separate counter.

</details>

## Quick Start

```bash
git clone https://github.com/siddhant-rajhans/payments-ledger-api.git
cd payments-ledger-api
docker compose up --build
```

The API is at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Create accounts and transfer

```bash
# Create two accounts
ALICE=$(curl -s -X POST http://localhost:8000/accounts \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "currency": "USD"}' | jq -r .id)

BOB=$(curl -s -X POST http://localhost:8000/accounts \
  -H "Content-Type: application/json" \
  -d '{"name": "Bob", "currency": "USD", "allow_overdraft": true}' | jq -r .id)

# Transfer 50.00 USD (5000 cents) with idempotency key
curl -X POST http://localhost:8000/transfers \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: txn-001" \
  -d "{\"from_account_id\": \"$BOB\", \"to_account_id\": \"$ALICE\", \"amount\": 5000}"

# Retry the same request (returns cached result, no double charge)
curl -X POST http://localhost:8000/transfers \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: txn-001" \
  -d "{\"from_account_id\": \"$BOB\", \"to_account_id\": \"$ALICE\", \"amount\": 5000}"

# Verify balances
curl -s http://localhost:8000/accounts/$ALICE | jq .balance  # 5000
curl -s http://localhost:8000/accounts/$BOB | jq .balance     # -5000

# Run reconciliation
curl -s http://localhost:8000/reconciliation | jq .
```

### Run tests

```bash
# Start Postgres
docker compose up -d db

# Run the test suite
make test
```

### Run the benchmark

```bash
docker compose up -d
python scripts/run_benchmark.py --transfers 1000 --concurrency 32
```

## Tests

```
tests/test_transfers.py       7 tests  CRUD, overdraft, reversal
tests/test_idempotency.py     3 tests  dedup, retry storm, distinct keys
tests/test_concurrency.py     3 tests  parallel transfers, overdraft races, bidirectional
tests/test_property.py        2 tests  global balance invariant, reversal restoration
tests/test_reconciliation.py  2 tests  empty and post-transfer reconciliation
```

## Project Structure

```
payments-ledger-api/
├── src/ledger/
│   ├── app.py                 # FastAPI app factory with table auto-creation
│   ├── config.py              # Pydantic settings (DATABASE_URL)
│   ├── database.py            # Async engine and session factory
│   ├── models.py              # Account, Transfer, JournalEntry (SQLAlchemy 2.0)
│   ├── schemas.py             # Pydantic request/response models
│   ├── api/
│   │   ├── accounts.py        # Account CRUD with computed balance
│   │   ├── transfers.py       # Transfers with idempotency and concurrency
│   │   ├── reconciliation.py  # Balance reconciliation endpoint
│   │   └── health.py          # Health check
│   └── services/
│       ├── transfer.py        # Double-entry logic, row locking, idempotency
│       └── reconciliation.py  # Global debit/credit verification
├── tests/
│   ├── test_transfers.py      # 7 tests: CRUD, overdraft, reversal
│   ├── test_idempotency.py    # 3 tests: dedup, retry storm, distinct keys
│   ├── test_concurrency.py    # 3 tests: parallel transfers, overdraft races, bidirectional
│   ├── test_property.py       # 2 tests: global balance invariant, reversal restoration
│   └── test_reconciliation.py # 2 tests: empty and post-transfer reconciliation
├── scripts/
│   └── run_benchmark.py       # Throughput and latency benchmark
├── docker-compose.yml         # Postgres + API
├── Dockerfile
├── Makefile                   # test, lint, format, run, bench, clean
└── pyproject.toml
```

## Tech Stack

- **FastAPI** with async endpoints and dependency injection
- **SQLAlchemy 2.0** async ORM with `asyncpg` driver
- **PostgreSQL 16** with `SELECT ... FOR UPDATE` row locking
- **Pydantic v2** for request/response validation and settings
- **pytest + pytest-asyncio + httpx** for async integration tests
- **Hypothesis** available for property-based testing

## License

MIT

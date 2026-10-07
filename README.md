# Usage metering & billing service

- Ingests usage events in idempotent batches and assigns each one to the customer's monthly billing cycle.
- Keeps per-cycle counters that fire 50 / 80 / 100 % allowance notifications through an outbox worker.
- Closes cycles into immutable invoices rated from the raw events (overage-only pricing, integer paise).
- Late events are billed as adjustment lines on the next invoice.
- FastAPI + SQLAlchemy 2 + Postgres 16 backend, React 18 + Ant Design dashboard; everything runs with one `docker compose up --build`.

## Contents

- [Demo videos](#demo-videos)
- [1. Quick start](#1-quick-start)
  - [Run it](#run-it)
  - [Load the 500K sample events](#load-the-500k-sample-events)
  - [Run the tests](#run-the-tests)
  - [Run without Docker](#run-without-docker)
- [2. Architecture](#2-architecture)
- [3. Lifecycle of one event](#3-lifecycle-of-one-event)
- [4. Design decisions & trade-offs](#4-design-decisions--trade-offs)
  - [API design](#api-design)
  - [Idempotency key](#idempotency-key)
  - [Event-time vs receipt-time](#event-time-vs-receipt-time)
  - [Money](#money)
  - [Timezones](#timezones)
  - [Cycle anchoring](#cycle-anchoring)
  - [Aggregation strategy](#aggregation-strategy)
  - [Thresholds & outbox](#thresholds--outbox)
  - [Late-event policy](#late-event-policy)
  - [Invoice immutability](#invoice-immutability)
  - [Mid-cycle plan change (designed for, not implemented)](#mid-cycle-plan-change-designed-for-not-implemented)
  - [Batch cap](#batch-cap)
  - [Future tolerance](#future-tolerance)
  - [Simple API key](#simple-api-key)
  - [Polling vs push](#polling-vs-push)
  - [Force-close (demo convenience)](#force-close-demo-convenience)
- [5. API reference](#5-api-reference)
- [6. Testing](#6-testing)
- [7. Out of scope / not built](#7-out-of-scope--not-built)
- [8. Demo video checklist](#8-demo-video-checklist)
  - [Scene 1 — Idempotent ingestion (accepted / duplicate / rejected)](#scene-1--idempotent-ingestion-accepted--duplicate--rejected)
https://github.com/user-attachments/assets/412e86ad-c27e-42a9-88de-7e379bf30d15
  - [Scene 2 — Thresholds and the outbox](#scene-2--thresholds-and-the-outbox)
https://github.com/user-attachments/assets/5651f1ed-4d46-42bd-947c-673a6316093d
  - [Scene 3 — Close a cycle, read the invoice](#scene-3--close-a-cycle-read-the-invoice)
https://github.com/user-attachments/assets/794e99f8-fc0c-4bee-ade4-b2cecddf2b25
  - [Scene 4 — Late event → adjustment on the next invoice](#scene-4--late-event--adjustment-on-the-next-invoice)
https://github.com/user-attachments/assets/d2c8a02b-1495-4a9b-b9ba-a21c9c74067a

Suggested review path: [Lifecycle of one event](#3-lifecycle-of-one-event), then
[Idempotency key](#idempotency-key), [Timezones](#timezones), [Late-event policy](#late-event-policy)
and [Aggregation strategy](#aggregation-strategy).

## Demo videos

| Scene | What it shows | Video |
|---|---|---|
| 1 | Re-sending the same batch doesn't change the numbers | [scene1-idempotent-ingestion.mp4](docs/demo/scene1-idempotent-ingestion.mp4) |
| 2 | 50 / 80 / 100 % notifications fire once each per cycle | [scene2-thresholds-fire-once.mp4](docs/demo/scene2-thresholds-fire-once.mp4) |
| 3 | Closing a cycle produces an invoice; closing it twice doesn't double-bill | [scene3-invoice-generation.mp4](docs/demo/scene3-invoice-generation.mp4) |
| 4 | A late event is billed as an adjustment on the next invoice | [scene4-late-event-adjustment.mp4](docs/demo/scene4-late-event-adjustment.mp4) |

---

## 1. Quick start

### Run it

```sh
docker compose up --build
```

| What | Where |
|---|---|
| Dashboard | http://localhost:5173 |
| API (FastAPI, OpenAPI at `/docs`) | http://localhost:8000 |
| Postgres — user `billing`, password `billing`; database `billing` (app) and `billing_test` (integration tests) | localhost:5432 |

- `api` startup (`backend/entrypoint.sh`): `alembic upgrade head` → `python -m app.cli seed` (idempotent upsert of 2 plans, 2 meters, 5 customers) → `uvicorn`.
- `db` runs `db/init/01-test-db.sql` on first start, creating `billing_test` for the integration tests.
- All secured calls need `X-API-Key: dev-key` (set by `API_KEY` in `docker-compose.yml`).

### Load the 500K sample events

```sh
docker compose run --rm api python -m app.cli generate --events 500000 --out sample-data/events.jsonl.gz --seed 42
docker compose run --rm api python -m app.cli load --file sample-data/events.jsonl.gz --batch-size 5000
```

- `events.jsonl.gz` is already in the repo, so `generate` is optional (only to regenerate with a different seed/size); `load` is the command to run.
- Run `docker compose up --build` once before this: `docker compose run` replaces the container command, so migrations and seed do not run inside it.
- `./backend/sample-data` is bind-mounted at `/app/sample-data`, so the `.gz` file lands on the host and is committed as the sample data.
- The loader goes through the same `services.ingest.ingest_batch` as the API.
- It prints `received / accepted / duplicate / rejected / thresholds_fired` plus elapsed seconds (progress every 10 batches).
- ~2 % of the lines are deliberate duplicates: expect `duplicate ≈ 10000`, `rejected = 0`.
- Other CLI commands: `python -m app.cli seed`, `rebuild-counters`, `close-due`.

### Run the tests

```sh
docker compose run --rm -e TEST_DATABASE_URL=postgresql+psycopg://billing:billing@db:5432/billing_test api pytest --cov=app --cov-report=term-missing
```

- Unit tests (pure domain) need no database; the integration suite is skipped as a whole when `TEST_DATABASE_URL` is unset.
- The integration session drops and re-migrates the test database, then truncates and re-seeds before every test. Never point `TEST_DATABASE_URL` at `billing`.

### Run without Docker

Backend (Python 3.12):

```sh
docker compose up -d db                      # or any Postgres with the two databases
cd backend
python -m venv .venv && . .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://billing:billing@localhost:5432/billing   # or put it in backend/.env
alembic upgrade head
python -m app.cli seed
uvicorn app.main:app --reload --port 8000
```

Frontend (Node 20):

```sh
cd frontend
cp .env.example .env        # VITE_API_KEY=dev-key
npm install
npm run dev                 # http://localhost:5173, Vite proxies /api → http://localhost:8000
```

Backend environment variables (`backend/app/config.py`, read from env or `backend/.env`):

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://billing:billing@localhost:5432/billing` | SQLAlchemy URL (psycopg3) |
| `API_KEY` | `dev-key` | value expected in `X-API-Key` |
| `WEBHOOK_URL` | `http://localhost:8000/api/v1/webhook-receiver` | where threshold notifications are POSTed |
| `FUTURE_TOLERANCE_SECONDS` | `300` | `occurred_at` may be at most this far in the future |
| `MAX_BATCH_SIZE` | `1000` | events per `POST /events/batch` before 413 |
| `NOTIFIER_POLL_SECONDS` | `2.0` | outbox worker poll interval |
| `NOTIFIER_MAX_ATTEMPTS` | `8` | delivery attempts before a notification is abandoned |
| `THRESHOLDS` | `(50, 80, 100)` | percent-of-allowance thresholds (JSON list in env, e.g. `[50,80,100]`) |

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Browser  →  web container  (localhost:5173)                 │
│  React SPA · antd · React Query (polls 10 s) · Zustand       │
│  nginx serves the SPA and forwards /api/* to the api         │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP  /api/v1/*   (X-API-Key)
┌──────────────────────────────▼───────────────────────────────┐
│  api container  (localhost:8000)  — FastAPI                  │
│                                                              │
│  1. api/        routes + schemas    HTTP in/out · status     │
│        │                                                     │
│  2. services/   ingest · usage · invoicing · notifications   │
│        │   │    counters · seed     the workflows            │
│        │   │                                                 │
│        │   └──► 3. domain/   cycles · validation · rating    │
│        │                     thresholds · money              │
│        │                     PURE: no DB, unit-tested alone  │
│        ▼                                                     │
│  4. db/         SQLAlchemy models · Alembic migrations       │
│                                                              │
│  workers/notifier  (background task, every 2 s)              │
│        reads unsent threshold rows → POSTs to WEBHOOK_URL    │
└──────────────────────────────┬───────────────────────────────┘
                               │ SQL
┌──────────────────────────────▼───────────────────────────────┐
│  db container  —  Postgres 16  (localhost:5432)              │
│  raw usage_events = source of truth · counters · invoices    │
└──────────────────────────────────────────────────────────────┘
```

- Requests flow top to bottom: `services` call `domain` for billing rules (cycle dates, validation, pricing, thresholds) and `db` for storage.
- `domain/` never imports the database, so rating and cycle maths are tested without Postgres.
- Webhooks go to `WEBHOOK_URL`; by default that's the API's own `/api/v1/webhook-receiver` stub, which just logs them.

Where things live:

| Path | Responsibility |
|---|---|
| [`backend/app/api/`](backend/app/api/) | HTTP layer: routes, request/response schemas, API-key check |
| [`backend/app/services/`](backend/app/services/) | One module per use case (ingest, usage, invoicing, notifications); the only layer that talks to the DB |
| [`backend/app/domain/`](backend/app/domain/) | Pure billing rules (cycles, validation, rating, thresholds, money); no DB or FastAPI imports |
| [`backend/app/db/`](backend/app/db/) + [`backend/alembic/`](backend/alembic/) | ORM models and the migration that creates the schema |
| [`backend/app/workers/notifier.py`](backend/app/workers/notifier.py) | Outbox worker that delivers threshold webhooks |
| [`backend/app/cli.py`](backend/app/cli.py) | `seed`, `generate`, `load`, `rebuild-counters`, `close-due` |
| [`backend/tests/`](backend/tests/) | `unit/` (pure, no DB) and `integration/` (real Postgres) |
| [`frontend/src/features/`](frontend/src/features/) | UI slices (`usage`, `invoices`, `customers`), each with `api/` hooks, `components/`, `routes/` |

---

## 3. Lifecycle of one event

1. Client POSTs `{"events":[{event_id, customer_id, meter, quantity, occurred_at}]}` to `/api/v1/events/batch` with `X-API-Key` ([routes/events.py](backend/app/api/routes/events.py)).
   - Missing/invalid key → 401. Missing `events` key → 400 `validation_error`.
   - More than 1000 events → 413 `batch_too_large`.
2. [`services/ingest.ingest_batch`](backend/app/services/ingest.py) does two bulk reads for the whole batch:
   - customers + their plan meters (`customers ⟕ plan_meters WHERE id IN (...)`);
   - the set of already-invoiced `period_start`s per customer.
3. [`domain/validation.classify_event`](backend/app/domain/validation.py) runs per event on plain data:
   - shape → `invalid_event`; customer → `unknown_customer`;
   - meter not priced on the plan → `unknown_meter`; quantity not a positive int → `invalid_quantity`;
   - `occurred_at > now + 300 s` → `future_timestamp`.
4. [`domain/cycles.period_containing(signup_date, tz, occurred_at)`](backend/app/domain/cycles.py) stamps `billing_period_start`.
   - That is the UTC instant of local midnight on the anchor day.
   - If that period already has an invoice: period index `>= current − 1` → accepted with `is_late = true`.
   - Older → `late_event_too_old`.
5. A second copy of the same `event_id` inside the batch is marked `duplicate` before touching the DB.
6. Survivors go in with one multi-row `INSERT ... ON CONFLICT (event_id) DO NOTHING RETURNING event_id` (chunks of 1000).
   - Ids not returned already existed → `duplicate`; first write wins, the new payload is discarded.
7. For accepted, non-late events, quantities are summed per `(customer, meter, period_start)` and upserted into `usage_counters`.
   - `quantity = quantity + excluded.quantity RETURNING quantity` gives `before`/`after` per key in the same statement.
8. [`domain/thresholds.crossed_thresholds(before, after, allowance)`](backend/app/domain/thresholds.py) returns the percentages first reached by this batch.
   - One row per crossing is inserted into `threshold_notifications`.
   - `ON CONFLICT DO NOTHING` on `UNIQUE (customer_id, meter_id, period_start, threshold)` keeps it to one row.
9. Steps 6–8 commit together; any failure rolls the whole batch back.
   - The response is 200 if nothing was rejected, else 207, with a per-event `results` list.
10. Within 2 s the [notifier](backend/app/workers/notifier.py) picks the unsent row ([services/notifications.py](backend/app/services/notifications.py)).
    - Query: `sent_at IS NULL AND attempts < 8 AND next_attempt_at <= now`, `FOR UPDATE SKIP LOCKED`.
    - POSTs `{customer_id, meter, threshold, usage, allowance, period_start, fired_at}` to `WEBHOOK_URL`, then sets `sent_at`.
    - On failure it records `attempts += 1`, `last_error`, `next_attempt_at = now + 2^attempts s`.
11. Meanwhile `GET /customers/{id}/usage` ([services/usage.py](backend/app/services/usage.py)) sums the raw events of the current period, never the counter.
    - Query: `WHERE customer_id = ? AND billing_period_start = ?`.
    - The sums are rated with the same `domain/rating` code the invoice uses.
12. When the cycle has ended, a close call ([routes/cycles.py](backend/app/api/routes/cycles.py)) runs [`services/invoicing.close_cycle`](backend/app/services/invoicing.py).
    - Triggers: `POST /customers/{id}/cycles/close`, `POST /cycles/close-due`, or `python -m app.cli close-due`.
    - One `usage` line per plan meter: `overage_units = max(0, used − allowance)`, `amount = round_half_up(overage_units × rate)`.
    - Insert invoice + lines, commit.
    - `UNIQUE (customer_id, period_start)` turns a concurrent second close into "return the existing invoice".
13. Late path: an event accepted with `is_late = true` is stored with its original `billing_period_start` and skips steps 7–8.
    - At the next close, every earlier invoiced period of the customer is re-rated from raw events (late ones included).
    - `delta = new_amount − SUM(amount_minor of all lines already carrying that period_start)`.
    - If `delta ≠ 0` the new invoice gets an `adjustment` line with `adjusts_invoice_id`.
    - On that line: `quantity = late units`, `overage_units = new_overage − billed_overage`, `amount_minor = delta`.
    - A third close finds `delta = 0` and adds nothing.

---

## 4. Design decisions & trade-offs

### API design

- Resources, not verbs: `events/batch`, `customers/{id}/usage`, `customers/{id}/invoices`, `invoices/{id}`.
- The two state changes that are not CRUD (`cycles/close`, `admin/counters/rebuild`) are explicit POST actions.
- Batch status codes: 200 all accepted/duplicate; 207 at least one rejected (body identical in shape, so clients parse once).
- 400 envelope malformed: `RequestValidationError` is remapped so the body is the same `{"error": {...}}` envelope everywhere.
- 413 over the cap.
- Per-event errors never fail the batch; a client with one bad row still gets the other 999 stored.
- One error shape everywhere: `{"error": {"code", "message", "details"?}}`. Even Starlette's own 404/405 are rewritten into it (`code: "http_error"`).
- I chose a plain `events: list[Any]` in the envelope and validate each item in the domain.
- So Pydantic cannot reject the whole batch because of one malformed item.
- Code:
  - [backend/app/api/routes/events.py](backend/app/api/routes/events.py)
  - [backend/app/api/schemas/events.py](backend/app/api/schemas/events.py)
  - [backend/app/main.py](backend/app/main.py) — exception handlers / error envelope
  - [backend/app/errors.py](backend/app/errors.py)

### Idempotency key

- The client generates `event_id`; it is the global primary key of `usage_events`.
- `INSERT ... ON CONFLICT (event_id) DO NOTHING RETURNING event_id`: no read-before-write, no race, one round trip per 1000 rows.
- First write wins. A repeat with a different payload is reported `duplicate` and ignored; I would rather surface a client bug than silently re-bill.
- A missing or empty `event_id` is `invalid_event`, never auto-generated: an auto-generated id would make a retry a double-count.
- Duplicates inside one batch are caught in memory before the insert so the counter bump counts each id once.
- Code:
  - [backend/app/services/ingest.py](backend/app/services/ingest.py)
  - [backend/alembic/versions/0001_initial.py](backend/alembic/versions/0001_initial.py) — `event_id` primary key
  - [backend/tests/integration/test_ingest.py](backend/tests/integration/test_ingest.py)

### Event-time vs receipt-time

| Decision | Uses |
|---|---|
| Which billing cycle an event belongs to (`billing_period_start`) | `occurred_at` |
| `future_timestamp` check | `occurred_at` vs receipt `now` |
| Late / too-old classification | `occurred_at`'s period vs the invoices that exist at receipt time |
| Counter bump and threshold crossing | `occurred_at`'s period, evaluated at receipt time |
| Invoice rating, current-usage read, daily chart buckets | `occurred_at` (chart buckets are local dates) |
| Deduplication | neither: `event_id` |
| Notification `created_at` / `fired_at`, retry schedule | receipt / wall-clock time |
| `received_at` column | stored only, for audit ("when did we learn about it") |

- Code:
  - [backend/app/domain/validation.py](backend/app/domain/validation.py)
  - [backend/app/services/ingest.py](backend/app/services/ingest.py)
  - [backend/app/services/usage.py](backend/app/services/usage.py) — chart buckets

### Money

- Amounts are integer paise (`bigint`), never floats; totals are plain integer sums.
- Rates are `Decimal` in Python and `NUMERIC(14,6)` in Postgres, in paise per unit (`50.000000` = ₹0.50/call).
- So sub-paisa rates are representable.
- Rounding happens exactly once per invoice line, `ROUND_HALF_UP` on `overage_units × rate`.
- Example: 1234 units × 0.2 paise = 246.8 → 247 paise; per-unit rounding would give 0.
- The usage page reuses the same `rate_meter` function, so "cost so far" always matches what the invoice will say.
- Code:
  - [backend/app/domain/money.py](backend/app/domain/money.py)
  - [backend/app/domain/rating.py](backend/app/domain/rating.py)
  - [backend/app/db/models.py](backend/app/db/models.py) — `BigInteger` amounts, `Numeric(14, 6)` rates

### Timezones

- A cycle boundary is local midnight on the anchor day in the customer's IANA zone, converted to UTC once (`period_start_utc`).
- Everything else compares UTC instants.
- Why: events arrive in UTC, so I convert the two boundaries, not the 500K events.
- `billing_period_start` is stamped at ingest, so invoice and usage queries are an equality on `(customer_id, billing_period_start)`.
- That keeps the index usable; a `timezone()` call on `occurred_at` in the `WHERE` would not.
- One pure function, `period_containing`, is the only place that knows about zones.
- It is unit-tested on the Kolkata half-hour offset and New York DST (23 h / 25 h cycle months).
- Example (`cus_asha`, signup 2026-01-10, Asia/Kolkata): cycle 1 starts `2026-02-09T18:30:00Z`.
- An event at `2026-02-09T20:00Z` is already "10 Feb" in Kolkata and belongs to cycle 1; one at `18:00Z` belongs to cycle 0.
- Stripe contrast: Stripe anchors a subscription to the exact timestamp it was created (`billing_cycle_anchor`).
- So Stripe's boundaries are UTC instants, not local dates.
- I chose local midnight because the dashboard and invoice have to read "10 Feb – 09 Mar" in the customer's own calendar.
- The cost is that cycle lengths vary by an hour across DST, which the tests pin down.
- Code:
  - [backend/app/domain/cycles.py](backend/app/domain/cycles.py)
  - [backend/tests/unit/test_cycles.py](backend/tests/unit/test_cycles.py)

### Cycle anchoring

- Monthly, anchored to the `signup_date` day. When that day does not exist in a month, clamp to the month's last day (31 Jan → 28 Feb).
- Cycle N is always `signup_date + N months`, never "previous boundary + 1 month", so the clamp never accumulates: 31 Jan → 28 Feb → 31 Mar → 30 Apr.
- `period_index_at` brackets an instant by starting from the calendar month difference and walking at most one step.
- `previous_period` / `next_period` are index arithmetic.
- Code: [backend/app/domain/cycles.py](backend/app/domain/cycles.py)

### Aggregation strategy

- Raw `usage_events` are the truth.
- Invoices, the usage page and the chart all aggregate raw rows at read time with `SUM(quantity) ... GROUP BY`.
- They go over `ix_usage_events_customer_period (customer_id, billing_period_start)`.
- `usage_counters` exists only for the per-batch threshold check (it gives `before`/`after` in one upsert). It is a cache.
- `python -m app.cli rebuild-counters` or `POST /admin/counters/rebuild` does `TRUNCATE + INSERT ... SELECT GROUP BY` over non-late events.
- `test_rebuild_counters_equals_live_counters` proves the rebuild matches the live values.
- Rule I set myself: pre-aggregate reads only if a read exceeds ~200 ms or the table passes tens of millions of rows.

**Measured** (Docker Desktop on Windows, Postgres 16, 490K events loaded, after `ANALYZE usage_events`):

| What | Result |
|---|---|
| Load: 500,000 events in 100 batches of 5,000 | 490,000 accepted · 10,000 duplicates · 0 rejected · 411 s (~1,200 events/s) |
| Per-customer cycle sum (`cus_asha`, current cycle, 13,230 rows) | Bitmap Index Scan on `ix_usage_events_customer_period` · **11 ms** |
| Daily timeseries (same customer and cycle, 28 days) | Same index · **34 ms** |

- Both read queries are well under the 200 ms rule, so I did not add pre-aggregated read tables.
- The timeseries query is slower because it converts each row to the customer's local date before grouping.
- Ingest throughput is bounded by one transaction per batch (insert + counter upsert + threshold rows).
  - The next step, if needed: larger batches or `COPY` into a staging table.

Reproduce:

```sql
-- docker compose exec db psql -U billing -d billing
ANALYZE usage_events;

EXPLAIN ANALYZE
SELECT meter_id, SUM(quantity) FROM usage_events
WHERE customer_id = 'cus_asha' AND billing_period_start = '2026-09-09 18:30:00+00'
GROUP BY meter_id;

EXPLAIN ANALYZE
SELECT (timezone('Asia/Kolkata', occurred_at))::date AS day, SUM(quantity) FROM usage_events
WHERE customer_id = 'cus_asha' AND meter_id = 'api_calls' AND billing_period_start = '2026-09-09 18:30:00+00'
GROUP BY 1;
```

- Code:
  - [backend/app/services/usage.py](backend/app/services/usage.py) — read-time sums
  - [backend/app/services/counters.py](backend/app/services/counters.py) — rebuild
  - [backend/app/api/routes/admin.py](backend/app/api/routes/admin.py)
  - [backend/alembic/versions/0001_initial.py](backend/alembic/versions/0001_initial.py) — `ix_usage_events_customer_period`
  - [backend/tests/integration/test_counters.py](backend/tests/integration/test_counters.py)

### Thresholds & outbox

- 50 / 80 / 100 % of each meter's allowance, once per customer × meter × cycle.
- "Once" is the database's job: `UNIQUE (customer_id, meter_id, period_start, threshold)` + `ON CONFLICT DO NOTHING`.
- So replays, concurrent batches and rebuilds cannot double-fire.
- Crossing uses integer arithmetic (`before × 100 < allowance × t ≤ after × 100`); one big batch can fire 50, 80 and 100 together.
- Ingestion only inserts the row and commits with the events.
- The notifier (an asyncio task started by the FastAPI lifespan) polls every 2 s.
- It locks up to 100 due rows with `FOR UPDATE SKIP LOCKED`, POSTs each with a 5 s timeout, and records the outcome.
- Backoff is `2^attempts` seconds; after 8 attempts (~8.5 min total) the row is left with its `last_error` and skipped.
- Ingestion latency never depends on the webhook endpoint being up.
- The default `WEBHOOK_URL` is the API's own `/api/v1/webhook-receiver` stub.
- The stub logs `webhook received ...`, so deliveries are visible in `docker compose logs api`.
- Code:
  - [backend/app/domain/thresholds.py](backend/app/domain/thresholds.py) — crossing arithmetic
  - [backend/app/services/ingest.py](backend/app/services/ingest.py) — row insert with `ON CONFLICT DO NOTHING`
  - [backend/app/services/notifications.py](backend/app/services/notifications.py) — delivery, backoff
  - [backend/app/workers/notifier.py](backend/app/workers/notifier.py) — poll loop
  - [backend/app/api/routes/webhook.py](backend/app/api/routes/webhook.py) — receiver stub
  - [backend/tests/integration/test_thresholds_db.py](backend/tests/integration/test_thresholds_db.py)

### Late-event policy

- Chosen: accept the event if its period is already invoiced but is the cycle immediately before the customer's current open cycle.
- The same applies to the current cycle itself after a force-close.
- Store it with `is_late = true` and its original `billing_period_start`.
- Do not touch counters or thresholds (that cycle's notifications are history).
- At the next close, re-rate every earlier invoiced period from raw events at that period's own allowance and rate.
- Bill only the delta as an `adjustment` line on the new invoice (`adjusts_invoice_id` points back).
- The delta subtracts every line already carrying that `period_start` (usage + earlier adjustments).
- So a late event is billed exactly once, with no "already billed" flag on events.
- Cutoff: periods older than one cycle back are rejected with `late_event_too_old`.
- It bounds how far back a close has to look and matches a one-month dispute window.
- What it does not touch: the closed invoice (immutable), `usage_counters`, threshold rows, the current period's usage figures.
- Late usage that stays within the allowance produces no line at all (tested).
- Rejected alternatives:
  - Reject anything after close: loses real usage, and clients retrying a queue would be penalised for my latency.
  - Reopen and reissue the invoice: breaks immutability and whatever accounting already consumed it.
  - Bill late events in the period they were received: wrong allowance and wrong rate, and the chart would show usage on the wrong days.
  - Hold every close for a grace window: delays all invoices for the rare late event; the adjustment line costs nothing when there is none.
- Code:
  - [backend/app/domain/validation.py](backend/app/domain/validation.py) — accept / `late_event_too_old`
  - [backend/app/services/invoicing.py](backend/app/services/invoicing.py) — `_adjustment_lines`
  - [backend/tests/unit/test_validation.py](backend/tests/unit/test_validation.py)
  - [backend/tests/integration/test_invoicing.py](backend/tests/integration/test_invoicing.py)

### Invoice immutability

- There is no UPDATE or DELETE path for `invoices` or `invoice_lines` anywhere in the code (no route, no service, no cascade).
- `status` is always `issued`.
- Corrections are new facts: adjustment lines on later invoices. The audit trail stays linear.
- Double close is safe by constraint: `UNIQUE (customer_id, period_start)`; the second caller gets the first invoice with 200.
- Code:
  - [backend/app/services/invoicing.py](backend/app/services/invoicing.py)
  - [backend/app/api/routes/invoices.py](backend/app/api/routes/invoices.py) — read-only routes
  - [backend/alembic/versions/0001_initial.py](backend/alembic/versions/0001_initial.py) — `uq_invoices_customer_period`

### Mid-cycle plan change (designed for, not implemented)

- A plan change would be stored as a dated `customer_plans` row (`customer_id, plan_id, effective_from`) instead of the single `customers.plan_id`.
- At close, the cycle is split at the change instant into plan periods.
- Each meter's allowance is prorated by whole days in each sub-period, rounded down.
- Rounding down means the customer is never charged for a partial day's allowance twice.
- Usage is summed per sub-period from `occurred_at`.
- The invoice gets one `usage` line per meter per plan period, each carrying its own `period_start`/`period_end`, allowance and rate.
- The threshold counters would restart at the split.
- Nothing in the current schema blocks this: `invoice_lines` already carries per-line period bounds and rates.
- Code:
  - [backend/app/db/models.py](backend/app/db/models.py) — `customers.plan_id`, `InvoiceLine` period bounds and rate
  - [backend/alembic/versions/0001_initial.py](backend/alembic/versions/0001_initial.py)

### Batch cap

- 1000 events → anything larger is 413 `batch_too_large` before any work.
- Keeps one transaction and one multi-row insert bounded.
- The CLI loader bypasses the HTTP cap and uses 5000-row batches against the same service.
- Code:
  - [backend/app/api/routes/events.py](backend/app/api/routes/events.py) — the 413 check
  - [backend/app/cli.py](backend/app/cli.py) — `load --batch-size`

### Future tolerance

- `occurred_at > now + FUTURE_TOLERANCE_SECONDS` (default 300) → `future_timestamp`.
- Five minutes absorbs client clock skew without letting a client pre-book next month's usage.
- Naive datetimes (no offset) are `invalid_event`; I refuse to guess a zone.
- Code:
  - [backend/app/domain/validation.py](backend/app/domain/validation.py)
  - [backend/app/config.py](backend/app/config.py) — `FUTURE_TOLERANCE_SECONDS`

### Simple API key

- One shared `X-API-Key` compared with `secrets.compare_digest`; `/health` and the webhook stub are open.
- Enough for a single-tenant demo; per-customer keys/scopes are out of scope.
- Code: [backend/app/api/deps.py](backend/app/api/deps.py) — `require_api_key`

### Polling vs push

- The dashboard polls usage, chart and notifications every 10 s with React Query (`refetchInterval`).
- Cheap to reason about, works through the nginx proxy, no connection state; the reads are indexed sums.
- WebSockets/SSE would be the next step if sub-second freshness mattered.
- Code:
  - [frontend/src/config.ts](frontend/src/config.ts) — `USAGE_POLL_INTERVAL_MS`
  - [frontend/src/features/usage/api/get-usage.ts](frontend/src/features/usage/api/get-usage.ts)
  - [frontend/src/features/usage/api/get-timeseries.ts](frontend/src/features/usage/api/get-timeseries.ts)
  - [frontend/src/features/usage/api/get-notifications.ts](frontend/src/features/usage/api/get-notifications.ts)

### Force-close (demo convenience)

- `POST /customers/{id}/cycles/close` with `{"force": true}` closes the current, still-running cycle "as of now".
- It uses the cycle's real period bounds (the invoice still says 10 Mar – 09 Apr).
- It exists so the demo can show an invoice without waiting a month, and the UI's "Close cycle" button uses it.
- Events that then arrive for that cycle are treated as late (adjustment on the next close).
- Not for production.
- Code:
  - [backend/app/api/routes/cycles.py](backend/app/api/routes/cycles.py)
  - [frontend/src/features/usage/components/CloseCycleButton.tsx](frontend/src/features/usage/components/CloseCycleButton.tsx)
  - [frontend/src/features/usage/api/close-cycle.ts](frontend/src/features/usage/api/close-cycle.ts)

---

## 5. API reference

- Base path `/api/v1`, JSON in and out. All routes except `GET /health` and `POST /api/v1/webhook-receiver` require `X-API-Key`.
- Error envelope: `{"error": {"code": "...", "message": "...", "details": [...]?}}`.

| Status | `code` | When |
|---|---|---|
| 400 | `validation_error` | request body/query does not match the schema (`details` lists Pydantic errors) |
| 400 | `invalid_period_start` | `period_start` is not the exact UTC start of one of the customer's cycles |
| 401 | `unauthorized` | missing/invalid `X-API-Key` |
| 404 | `customer_not_found`, `invoice_not_found`, `unknown_meter` | path/query refers to nothing |
| 404 / 405 | `http_error` | unknown route / wrong method |
| 409 | `cycle_not_ended` | closing a cycle whose end is in the future without `force` |
| 413 | `batch_too_large` | more than `MAX_BATCH_SIZE` events |

### `GET /health` — no key

`200 {"status": "ok"}`

### `POST /api/v1/events/batch`

```sh
curl -s -X POST localhost:8000/api/v1/events/batch -H "X-API-Key: dev-key" -H "Content-Type: application/json" -d '{
  "events": [
    {"event_id": "evt_1", "customer_id": "cus_asha", "meter": "api_calls", "quantity": 3, "occurred_at": "2026-03-15T10:00:00Z"},
    {"event_id": "evt_2", "customer_id": "cus_nobody", "meter": "api_calls", "quantity": 1, "occurred_at": "2026-03-15T10:00:00Z"},
    {"customer_id": "cus_asha"}
  ]}'
```

`207` (would be `200` if nothing were rejected):

```json
{
  "summary": {"received": 3, "accepted": 1, "duplicate": 0, "rejected": 2},
  "results": [
    {"event_id": "evt_1", "status": "accepted"},
    {"event_id": "evt_2", "status": "rejected", "error": {"code": "unknown_customer", "message": "unknown customer 'cus_nobody'"}},
    {"event_id": null, "status": "rejected", "error": {"code": "invalid_event", "message": "event_id must be a non-empty string"}}
  ]
}
```

- `status`: `accepted` | `duplicate` | `rejected`.
- `is_late: true` appears only on late accepted events; `error` only on rejected ones; `event_id` is `null` when the row had no usable id.
- Per-event `error.code`: `invalid_event`, `unknown_customer`, `unknown_meter`, `invalid_quantity`, `future_timestamp`, `late_event_too_old`.
- Whole-request: 400 `validation_error` (e.g. `{"items": []}`), 413 `batch_too_large`.

### `GET /api/v1/customers`

`200`:

```json
[{"id": "cus_asha", "name": "Asha Verma", "timezone": "Asia/Kolkata", "signup_date": "2026-01-10", "plan": {"id": "basic", "name": "Basic"}}]
```

### `GET /api/v1/customers/{id}`

`200`: the list item plus

```json
"current_period": {"start": "2026-03-09T18:30:00Z", "end": "2026-04-09T18:30:00Z", "start_local": "2026-03-10T00:00:00+05:30", "end_local": "2026-04-10T00:00:00+05:30"}
```

404 `customer_not_found`.

### `GET /api/v1/customers/{id}/usage`

`200`:

```json
{
  "period": {"start": "...", "end": "...", "start_local": "...", "end_local": "..."},
  "currency": "INR",
  "meters": [
    {"meter": "api_calls", "display_name": "API calls", "unit": "call", "used": 12000, "allowance": 10000, "remaining": 0,
     "overage_units": 2000, "percent": 120.0, "state": "in_overage", "rate_minor": "50.000000", "cost_minor": 100000},
    {"meter": "storage_gb", "display_name": "Storage", "unit": "GB", "used": 3, "allowance": 10, "remaining": 7,
     "overage_units": 0, "percent": 30.0, "state": "within_allowance", "rate_minor": "300.000000", "cost_minor": 0}
  ],
  "total_cost_minor": 100000
}
```

- `state`: `within_allowance` (< 80 %), `approaching_limit` (80–< 100 %), `in_overage` (≥ 100 %).
- `percent` is truncated to 2 dp so display never crosses a band early.

### `GET /api/v1/customers/{id}/usage/timeseries?meter=api_calls`

`200`: daily sums for the current period in the customer's local dates, zero-filled up to today.

```json
{"meter": "api_calls", "bucket": "day", "points": [{"date": "2026-03-10", "quantity": 412}, {"date": "2026-03-11", "quantity": 0}]}
```

400 `validation_error` when `meter` is missing; 404 `unknown_meter` when the meter is not on the customer's plan.

### `GET /api/v1/customers/{id}/notifications[?all=true]`

`200`: current cycle by default, every cycle with `all=true`, newest first.

```json
[{"id": 7, "meter": "api_calls", "threshold": 80, "period_start": "2026-03-09T18:30:00Z", "usage_at_fire": 8120, "allowance": 10000,
  "created_at": "2026-03-20T09:12:44Z", "sent_at": "2026-03-20T09:12:46Z", "attempts": 0, "last_error": null}]
```

### `GET /api/v1/customers/{id}/invoices`

`200`, newest period first:

```json
[{"id": "inv_3f9c2a7b1d04", "customer_id": "cus_asha", "period_start": "2026-02-09T18:30:00Z", "period_end": "2026-03-09T18:30:00Z",
  "period_start_local": "2026-02-10T00:00:00+05:30", "period_end_local": "2026-03-10T00:00:00+05:30",
  "currency": "INR", "total_minor": 100000, "status": "issued", "issued_at": "2026-03-15T00:00:00Z"}]
```

### `GET /api/v1/invoices/{invoice_id}`

`200`: the invoice plus `lines`:

```json
"lines": [
  {"id": 1, "line_type": "usage", "meter": "api_calls", "display_name": "API calls", "period_start": "...", "period_end": "...",
   "quantity": 12000, "allowance": 10000, "overage_units": 2000, "rate_minor": "50.000000", "amount_minor": 100000,
   "description": "API calls: 12,000 call used, 10,000 included, 2,000 over allowance × ₹0.50 = ₹1,000.00", "adjusts_invoice_id": null},
  {"id": 3, "line_type": "adjustment", "meter": "api_calls", "display_name": "API calls", "period_start": "...", "period_end": "...",
   "quantity": 500, "allowance": 10000, "overage_units": 500, "rate_minor": "50.000000", "amount_minor": 25000,
   "description": "Late usage for 10 Feb – 09 Mar 2026 (received after invoice inv_3f9c2a7b1d04)", "adjusts_invoice_id": "inv_3f9c2a7b1d04"}
]
```

404 `invoice_not_found`.

On an adjustment line `quantity` is the late units, `overage_units` the change in billable units, `amount_minor` the delta (can be negative).

### `POST /api/v1/customers/{id}/cycles/close`

Body (all optional): `{"period_start": "<exact UTC cycle start>", "force": false}`.

- No body fields: closes the most recently ended cycle (the one before the current one).
- `period_start`: closes that specific cycle; must equal one of the customer's cycle starts (else 400 `invalid_period_start`).
- `force: true`: demo only, closes the current cycle as of now (also overrides the end check for an explicit `period_start`).

```sh
curl -s -X POST localhost:8000/api/v1/customers/cus_asha/cycles/close -H "X-API-Key: dev-key" -H "Content-Type: application/json" -d '{}'
```

`201` invoice (created) / `200` invoice (already existed, same body) / `409 cycle_not_ended` (cycle still running, or first cycle not ended).

### `POST /api/v1/cycles/close-due`

Closes, for every customer, the most recently ended cycle that has no invoice; each close commits on its own.

`200 {"closed": [{"customer_id": "cus_asha", "invoice_id": "inv_...", "period_start": "2026-02-09T18:30:00Z"}]}` (empty list when nothing is due).

### `POST /api/v1/admin/counters/rebuild`

`200 {"rows": 12}` — number of `usage_counters` rows after `TRUNCATE + INSERT ... SELECT` over non-late events.

### `POST /api/v1/webhook-receiver` — no key

Accepts any JSON object, logs `webhook received {...}` at INFO, returns `200 {"ok": true}`. Payload the notifier sends:

```json
{"customer_id": "cus_asha", "meter": "api_calls", "threshold": 80, "usage": 8120, "allowance": 10000,
 "period_start": "2026-03-09T18:30:00+00:00", "fired_at": "2026-03-20T09:12:44+00:00"}
```

---

## 6. Testing

```sh
docker compose run --rm -e TEST_DATABASE_URL=postgresql+psycopg://billing:billing@db:5432/billing_test api pytest --cov=app --cov-report=term-missing
# without docker, from backend/: TEST_DATABASE_URL=postgresql+psycopg://billing:billing@localhost:5432/billing_test pytest --cov=app --cov-report=term-missing
```

Result: **76 passed in ~20 s**, total coverage **80%**.

| Core logic | Coverage |
|---|---|
| `domain/rating.py`, `money.py`, `thresholds.py`, `validation.py` | 100% |
| `domain/cycles.py` | 98% |
| `services/counters.py` | 100% |
| `services/ingest.py` | 95% |
| `services/invoicing.py` | 93% |

The total is pulled down by the CLI (0%) and the notifier worker (42%); see "Not covered by tests" below.

Unit (`backend/tests/unit`, pure, no DB):

| File | Proves |
|---|---|
| [`test_money.py`](backend/tests/unit/test_money.py) | `to_minor` is ROUND_HALF_UP and returns `int`; `format_inr` / `format_inr_rate` output |
| [`test_cycles.py`](backend/tests/unit/test_cycles.py) | clamp without drift (31 Jan → 28 Feb → 31 Mar → 30 Apr); **`test_kolkata_boundary_event_in_utc_evening_belongs_to_next_local_cycle`** (event at `2026-02-09T20:00Z`, signup day 10 → cycle starting `2026-02-09T18:30Z`); New York DST cycles are 28 d − 1 h and 31 d + 1 h; `period_containing` brackets every instant; naive datetimes rejected; prev/next/current; local period labels |
| [`test_rating.py`](backend/tests/unit/test_rating.py) | no overage → 0; 12,000 vs 10,000 at ₹0.50 → ₹1,000.00; 1234 × 0.2 paise → 247 (rounded once, not per unit); amounts are `int`; one line per plan meter in plan order |
| [`test_thresholds.py`](backend/tests/unit/test_thresholds.py) | 0→85 fires 50 and 80; 85→90 nothing; 95→120 only 100; landing exactly on a threshold fires it; one jump can fire all three; `usage_state` bands; `percent_used` truncates |
| [`test_validation.py`](backend/tests/unit/test_validation.py) | valid event gets its period; `unknown_customer`, `unknown_meter` (incl. unpriced meter), `invalid_quantity` (0, −1, 1.5, "3", `True`), shape errors → `invalid_event`; future tolerance edge (300 s ok, 301 s rejected, 600 s config accepts); late accepted for previous cycle, rejected when older, normal when the old cycle is un-invoiced, late (not rejected) for a force-closed current cycle |

Integration (`backend/tests/integration`, real Postgres via Alembic, truncated + re-seeded per test):

| File | Proves |
|---|---|
| [`test_ingest.py`](backend/tests/integration/test_ingest.py) | **`test_reingesting_the_same_batch_does_not_move_the_numbers`** (same 50 events twice → 0 accepted / 50 duplicate, identical counters and `SUM`); duplicate with a different payload is `duplicate` and first write wins; in-batch duplicate counted once; retry after partial delivery inserts only the missing event; **`test_kolkata_event_in_utc_evening_belongs_to_the_next_local_day_cycle`** (stored `billing_period_start` and counter keys at `18:30Z` boundaries); 207 mixed batch with per-event codes in order; 200 clean batch; 413 oversize; 400 malformed envelope; 401 without key while `/health` stays open |
| [`test_thresholds_db.py`](backend/tests/integration/test_thresholds_db.py) | 50, 80, 100 fire exactly once across five batches plus a replayed batch, with `usage_at_fire` recorded; rows are per customer × meter × cycle |
| [`test_invoicing.py`](backend/tests/integration/test_invoicing.py) | close twice → one invoice, same `inv_` id; usage lines carry quantity/allowance/overage/rate/amount/period and the plain-language description for every plan meter; late event → `adjustment` line with `delta = 25,000` paise referencing the first invoice, counters untouched, and a third close adds nothing; late usage within allowance → no adjustment; too-old late event rejected while the previous cycle's is accepted; `close_due` invoices every customer's last ended cycle exactly once; route: force-close 201 then 200 with the same id, detail and list endpoints; 409 `cycle_not_ended` and 400 `invalid_period_start`; default body closes the most recently ended cycle |
| [`test_counters.py`](backend/tests/integration/test_counters.py) | `rebuild_counters` reproduces the live counters exactly (late event excluded from both); `POST /admin/counters/rebuild` reports the row count |

Not covered by tests:

- the notifier loop itself ([`workers/notifier.py`](backend/app/workers/notifier.py), exercised manually through the webhook stub logs);
- the CLI entry points;
- the frontend.

---

## 7. Out of scope / not built

- Mid-cycle plan changes (design above), base fees, tiered or volume pricing, minimum commitments, taxes, credits/prepaid balances.
- Payments, invoice PDFs, invoice numbering sequences, multiple currencies (everything is INR).
- Per-customer API keys, roles, rate limiting, request signing of webhooks, webhook endpoint per customer.
- Notification channels other than one webhook URL; alert deduplication across channels.
- Timeseries buckets other than `day`; pagination on list endpoints; event query/search API; event deletion or retention.
- Horizontal scaling of the notifier (the `SKIP LOCKED` query makes a second process safe, but only one runs, inside the API).
- Frontend tests, i18n, mobile layout polish.

---

## 8. Demo video checklist

Recorded videos: see [Demo videos](#demo-videos) at the top.

Setup before recording:

- `docker compose up --build`, then the generate + load commands from section 1.
- Open http://localhost:5173 (lands on `cus_asha`'s usage page).

### Scene 1 — Idempotent ingestion (accepted / duplicate / rejected)

```sh
curl -s -X POST localhost:8000/api/v1/events/batch -H "X-API-Key: dev-key" -H "Content-Type: application/json" -d '{
  "events": [
    {"event_id": "evt_demo_1", "customer_id": "cus_asha", "meter": "api_calls", "quantity": 25, "occurred_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"},
    {"event_id": "evt_demo_1", "customer_id": "cus_asha", "meter": "api_calls", "quantity": 99, "occurred_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"},
    {"event_id": "evt_demo_2", "customer_id": "cus_nobody", "meter": "api_calls", "quantity": 1, "occurred_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"},
    {"event_id": "evt_demo_3", "customer_id": "cus_asha", "meter": "api_calls", "quantity": 0, "occurred_at": "2099-01-01T00:00:00Z"}
  ]}' | jq
```

- Show: HTTP 207, `summary` 1 accepted / 1 duplicate / 2 rejected, per-event codes `unknown_customer`, `invalid_quantity`.
- Re-run the same command: `evt_demo_1` is now `duplicate`, nothing else changes.
- Show the cap: `curl -s -o /dev/null -w "%{http_code}\n" ... -d '{"events": [1000+ items]}'` → 413.
- Or mention it; `test_oversized_batch_returns_413` covers it.
- UI: Usage page for Asha Verma; the API calls card ticks up by 25 within 10 s (the "Auto-refreshes every 10 s" badge spins).

### Scene 2 — Thresholds and the outbox

- UI: switch the header dropdown to Noor Haddad (`cus_noor`, basic plan, ~90 % after the load).
- Show: orange "approaching limit" tag, progress bar, 50 % and 80 % rows in the "Threshold notifications" table with `sent_at` filled.
- Push Noor over 100 % (quantity large enough for the remaining allowance):

```sh
curl -s -X POST localhost:8000/api/v1/events/batch -H "X-API-Key: dev-key" -H "Content-Type: application/json" -d '{
  "events": [{"event_id": "evt_demo_noor_100", "customer_id": "cus_noor", "meter": "api_calls", "quantity": 2000, "occurred_at": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"}]}' | jq
```

- Within 10 s the card turns red "in overage" and a 100 % row appears.
- `docker compose logs -f api | grep "webhook received"` shows the POST landing on the stub with `"threshold": 100`.
- `curl -s localhost:8000/api/v1/customers/cus_noor/notifications -H "X-API-Key: dev-key" | jq` → `sent_at`, `attempts: 0`.
- Re-send the same event: duplicate, no second 100 % row (the UNIQUE constraint).

### Scene 3 — Close a cycle, read the invoice

- Close Asha's most recently ended cycle (the real one, not forced):

```sh
curl -s -i -X POST localhost:8000/api/v1/customers/cus_asha/cycles/close -H "X-API-Key: dev-key" -H "Content-Type: application/json" -d '{}'
```

- Show: `HTTP/1.1 201`, `total_minor`, `period_start_local` / `period_end_local` at `+05:30` midnight.
- Run it again: `HTTP/1.1 200`, same `id`.
- UI: Invoices tab → the invoice row → detail page: one line per meter, "N calls used · 10,000 included · M extra × ₹0.50 = ₹…", total.
- Mention: no edit/delete endpoint exists for invoices.

### Scene 4 — Late event → adjustment on the next invoice

- Pick a timestamp inside the cycle just closed in scene 3 (e.g. two days before the current period start shown by `GET /customers/cus_asha`), and send it:

```sh
curl -s -X POST localhost:8000/api/v1/events/batch -H "X-API-Key: dev-key" -H "Content-Type: application/json" -d '{
  "events": [{"event_id": "evt_demo_late", "customer_id": "cus_asha", "meter": "api_calls", "quantity": 400, "occurred_at": "<inside the closed cycle, e.g. 2026-03-01T10:00:00Z>"}]}' | jq
```

- Show: `"status": "accepted", "is_late": true`; the Usage page and the existing invoice do not change.
- Send one dated two cycles back → `late_event_too_old`.
- UI: Usage page → "Close cycle" button (top right) → confirm (demo-only force close of the current cycle) → success toast with the new invoice link → click it.
- Show: usage lines for the current cycle plus a purple "Adjustment" line: `400 calls received late · 400 extra × ₹0.50 = ₹200.00`.
- The adjustment line links back to the scene 3 invoice (`adjusts_invoice_id`).
- Close with: `python -m app.cli close-due` / `POST /cycles/close-due` would do the same for every customer on a schedule.

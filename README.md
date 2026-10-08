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
- [2. Architecture](#2-architecture)
- [3. Lifecycle of one event](#3-lifecycle-of-one-event)
- [4. Design decisions & trade-offs](#4-design-decisions--trade-offs)
  - [Late-event policy](#late-event-policy)
  - [Idempotency key](#idempotency-key)
  - [Event-time vs receipt-time](#event-time-vs-receipt-time)
  - [Timezones](#timezones)
  - [Aggregation strategy](#aggregation-strategy)
  - [Thresholds & outbox](#thresholds--outbox)
  - [Invoice immutability](#invoice-immutability)
  - [Money](#money)
  - [Cycle anchoring](#cycle-anchoring)
  - [Mid-cycle plan change (designed for, not implemented)](#mid-cycle-plan-change-designed-for-not-implemented)
  - [API design](#api-design)
- [5. API reference](#5-api-reference)
- [6. Testing](#6-testing)
- [7. Out of scope / not built](#7-out-of-scope--not-built)
- [8. Demo video checklist](#8-demo-video-checklist)

Suggested review path: [Late-event policy](#late-event-policy), then the [decisions at a glance](#4-design-decisions--trade-offs)
and the [lifecycle of one event](#3-lifecycle-of-one-event).

## Demo videos

**Scene 1 — Re-sending the same batch doesn't change the numbers**

https://github.com/user-attachments/assets/412e86ad-c27e-42a9-88de-7e379bf30d15

**Scene 2 — 50 / 80 / 100 % alerts fire once each per cycle**

https://github.com/user-attachments/assets/5651f1ed-4d46-42bd-947c-673a6316093d

**Scene 3 — Closing a cycle produces an invoice; closing twice doesn't double-bill**

https://github.com/user-attachments/assets/794e99f8-fc0c-4bee-ade4-b2cecddf2b25

**Scene 4 — A late event is billed as an adjustment on the next invoice**

https://github.com/user-attachments/assets/d2c8a02b-1495-4a9b-b9ba-a21c9c74067a

Downloadable copies: [scene1-idempotent-ingestion.mp4](docs/demo/scene1-idempotent-ingestion.mp4) · [scene2-thresholds-fire-once.mp4](docs/demo/scene2-thresholds-fire-once.mp4) · [scene3-invoice-generation.mp4](docs/demo/scene3-invoice-generation.mp4) · [scene4-late-event-adjustment.mp4](docs/demo/scene4-late-event-adjustment.mp4)

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

The sample file is already in the repo (`backend/sample-data/events.jsonl.gz`). With the stack running:

```sh
docker compose run --rm api python -m app.cli load --file sample-data/events.jsonl.gz
```

- Expected: 490,000 accepted, ~10,000 duplicates (deliberate 2 %), 0 rejected; about 7 minutes.
- Events go through the same ingest code as the API.
- To regenerate the file with another seed or size: `python -m app.cli generate --events 500000 --seed 42`.

### Run the tests

```sh
docker compose run --rm -e TEST_DATABASE_URL=postgresql+psycopg://billing:billing@db:5432/billing_test api pytest --cov=app --cov-report=term-missing
```

- Unit tests (pure domain) need no database; the integration suite is skipped as a whole when `TEST_DATABASE_URL` is unset.
- The integration session drops and re-migrates the test database, then truncates and re-seeds before every test. Never point `TEST_DATABASE_URL` at `billing`.

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

**1. The client sends a batch**
- `POST /api/v1/events/batch` with up to 1,000 events and the `X-API-Key` header ([routes/events.py](backend/app/api/routes/events.py)).
- Wrong key → 401 · malformed body → 400 · more than 1,000 events → 413.

**2. Each event is checked on its own** ([domain/validation.py](backend/app/domain/validation.py))
- Rejected if: unknown customer, meter not in the customer's plan, quantity not positive, or timestamp more than 5 minutes in the future.
- One bad event never fails the batch; it's reported and the rest continue.

**3. The event is placed in its billing cycle** ([domain/cycles.py](backend/app/domain/cycles.py))
- Using `occurred_at` and the customer's timezone (cycles start at local midnight on the signup day).
- If that cycle is already invoiced, the event is **late**: accepted if it's the previous cycle, rejected if older.

**4. Stored once** ([services/ingest.py](backend/app/services/ingest.py))
- `event_id` is the primary key, so a repeat (same batch, a retry, or a week later) is reported `duplicate` and not counted again.

**5. Counters and alerts update**
- The cycle's running total for that meter goes up (late events skip this).
- If the total crosses 50 %, 80 % or 100 % of the allowance, an alert row is saved, at most once per cycle ([domain/thresholds.py](backend/app/domain/thresholds.py)).

**6. One commit, one response**
- Steps 4–5 succeed or fail together, so a retried batch can never double-count.
- Response: 200 if nothing was rejected, 207 if some were, with a result per event.

**7. Alerts are delivered in the background** ([workers/notifier.py](backend/app/workers/notifier.py))
- A worker sends unsent alerts to the webhook every 2 s and retries failures; ingestion never waits for it.

**8. The dashboard shows live usage** ([services/usage.py](backend/app/services/usage.py))
- Usage is summed from the stored events and refreshed every 10 s: used, remaining, overage, cost so far.

**9. The cycle closes into an invoice** ([services/invoicing.py](backend/app/services/invoicing.py))
- One line per meter: used, included, extra units × rate = amount.
- Closing the same cycle again returns the same invoice; invoices are never edited.

**10. Late events become an adjustment**
- At the next close, the earlier cycle is re-priced with its late events.
- The difference from what was already billed is added as an adjustment line linked to the old invoice (see [Late-event policy](#late-event-policy)).

---

## 4. Design decisions & trade-offs

**At a glance**

| Topic | Decision |
|---|---|
| [Late events](#late-event-policy) | Accept; bill the difference as an adjustment on the next invoice; reject if older than one cycle |
| [Idempotency](#idempotency-key) | Client-sent `event_id` is the primary key; repeats are reported `duplicate` and never re-counted |
| [Event vs receipt time](#event-time-vs-receipt-time) | `occurred_at` decides the cycle; `received_at` decides lateness |
| [Timezones](#timezones) | Cycle starts at local midnight on the signup day, converted to UTC once; everything else compares UTC |
| [Aggregation](#aggregation-strategy) | Reads sum raw events (11–34 ms at 490K rows); counters exist only for the threshold check |
| [Thresholds](#thresholds--outbox) | Unique row per customer × meter × cycle × threshold; a background worker delivers |
| [Invoices](#invoice-immutability) | Never edited; closing twice returns the same invoice |
| [Money](#money) | Integer paise; rates as `NUMERIC`; rounded once per line |

### Late-event policy

**Decision:** accept the late event, leave the issued invoice untouched, and bill the difference as an adjustment line on the next invoice.

**Example** (`cus_asha`, basic plan: 10,000 calls included, ₹0.50 per extra call):

| When | What happens | Billed |
|---|---|---|
| 10 Sep: cycle 10 Aug – 10 Sep closes | 12,000 calls → 2,000 extra → invoice A | ₹1,000 |
| 15 Sep: 100 calls dated 5 Sep arrive (inside the closed cycle) | accepted with `is_late = true`; invoice A unchanged | — |
| 10 Oct: cycle 10 Sep – 10 Oct closes | old cycle re-rated: 12,100 calls → ₹1,050; already billed ₹1,000 → **adjustment line ₹50** on invoice B, pointing to A | +₹50 |
| 12 Nov: another event dated 5 Sep arrives | that cycle is now two cycles back → rejected `late_event_too_old` | — |

**Rules**

- Accepted only if its cycle is invoiced and is the one just before the current cycle (or the current cycle after a demo force-close).
- Stored with its true `billing_period_start`; it does not touch counters or threshold alerts (that cycle's alerts are history).
- At each close, earlier invoiced cycles are re-rated at their own allowance and rate; only the difference is billed.
- The difference subtracts everything already billed for that cycle, so a late event is billed exactly once.
- Late usage still within the allowance adds no line (difference ₹0).
- Older than one cycle back → rejected. Bills settle after one month, like a typical dispute window.

**Why not the alternatives**

| Alternative | Problem |
|---|---|
| Reject every late event | Loses real usage and revenue |
| Edit and reissue the old invoice | Breaks immutability |
| Count it as current usage | Wrong month's allowance and rate; chart shows it on the wrong day |
| Delay every close by a grace window | Slows all invoices for a rare case |

### Idempotency key

- The client generates `event_id`; it is the global primary key of `usage_events`.
- `INSERT ... ON CONFLICT (event_id) DO NOTHING RETURNING event_id`: no read-before-write, no race, one round trip per 1000 rows.
- First write wins. A repeat with a different payload is reported `duplicate` and ignored; I would rather surface a client bug than silently re-bill.
- A missing or empty `event_id` is `invalid_event`, never auto-generated: an auto-generated id would make a retry a double-count.
- Duplicates inside one batch are caught in memory before the insert so the counter bump counts each id once.

### Event-time vs receipt-time

Two times on every event:

- **`occurred_at`**: when the customer made the call (sent by the client).
- **`received_at`**: when we got it (set by the server).

**Rule: what the customer is billed for follows `occurred_at`. Whether an event is on time follows `received_at`.**

| Question | Answered by |
|---|---|
| Which billing month does this event belong to? | `occurred_at` |
| What goes on the invoice, the usage page and the chart? | `occurred_at` |
| Is it late (its month was already invoiced when it arrived)? | `received_at` |
| Is the timestamp in the future? | `occurred_at` compared with `received_at` |
| Is it a duplicate? | neither, only `event_id` |

Example (customer's local time, new cycle starts at midnight on the 10th): a call made at 23:50 on 9 Feb arrives at 00:10 on 10 Feb. It is billed in the old cycle, because it happened before midnight, even though it arrived after the new cycle started.

### Timezones

**Decision:** a customer's billing month starts at **midnight on their signup day, in their own timezone**. That moment is converted to UTC once; everything else works in UTC.

**Example** (`cus_asha`, signed up 10 Jan, India = UTC+5:30):

| | India time | UTC |
|---|---|---|
| New cycle starts | 10 Feb, 00:00 | 9 Feb, 18:30 |
| Event A | 9 Feb, 23:30 | 9 Feb, 18:00 → **old cycle** |
| Event B | 10 Feb, 01:30 | 9 Feb, 20:00 → **new cycle** |

Event B looks like "9 Feb" in UTC but is already 10 Feb for the customer, so it belongs to the new cycle.

**Why convert the boundary, not the events**
- Events arrive in UTC; converting 2 boundaries is cheaper than converting 500K events.
- Each event is tagged with its cycle when it arrives, so usage and invoice queries are a simple indexed lookup.

**Where the cycle is stored:** these columns hold the cycle boundary (local midnight, converted to UTC). All other timestamps are plain UTC.

| Column | Used for |
|---|---|
| `usage_events.billing_period_start` | Which cycle the event belongs to; usage and invoice sums filter on it |
| `usage_counters.period_start` | Which cycle the running total is for |
| `threshold_notifications.period_start` | So each alert fires once per cycle |
| `invoices.period_start` / `period_end` | The cycle the bill covers; one invoice per customer per cycle |
| `invoice_lines.period_start` / `period_end` | The cycle each line covers; for an adjustment, the old cycle being corrected |

**Compared with Stripe:** Stripe starts cycles at the exact UTC moment of signup, so a cycle can flip at, say, 7:53 pm local time. The assignment specifies cycles in the customer's timezone, so ours flip at local midnight and invoices read "10 Feb – 9 Mar".

### Aggregation strategy

**Question from the assignment:** did 500K events need pre-aggregation? **No, not for reads.**

- **Raw events are the source of truth.** The usage page, chart and invoices add up `usage_events` directly when asked, using an index on customer + cycle.
- **One small summary table, `usage_counters`,** keeps a running total per customer, meter and cycle. It's used only to spot a 50/80/100 % crossing quickly on each batch; nothing is billed from it.
- **It can be rebuilt from raw events at any time** (`rebuild-counters`), and a test proves the rebuilt values match.
- **My rule:** add pre-aggregated read tables only if a read takes over ~200 ms or the table grows to tens of millions of rows.

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

### Thresholds & outbox

**Decision:** alert at 50 %, 80 % and 100 % of each meter's allowance, **once per customer, meter and cycle**, without slowing ingestion.

**Fires once**
- Each alert is a row with a unique key (customer, meter, cycle, threshold), so the database refuses a second copy.
- Retries, replays and two batches at the same moment can't double-fire.
- A single large batch can cross several lines at once; each still fires once.

**Doesn't slow ingestion (outbox pattern)**
- Ingestion only saves the alert row, together with the events.
- A background worker sends unsent alerts to the webhook every 2 s.
- If the webhook is slow or down, only the worker waits: it retries with growing delays and gives up after 8 tries.
- Alerts are rows in Postgres, so they survive restarts and are sent when the app comes back.

**For this assignment** the webhook is a stub inside the API (`/api/v1/webhook-receiver`) that logs each alert; the dashboard shows each one as **Sent**.

### Invoice immutability

- There is no UPDATE or DELETE path for `invoices` or `invoice_lines` anywhere in the code (no route, no service, no cascade).
- Corrections are new facts: adjustment lines on later invoices. The audit trail stays linear.
- Double close is safe by constraint: `UNIQUE (customer_id, period_start)`; the second caller gets the first invoice with 200.

### Money

**Decision:** money is never a float. Amounts are whole paise; rates are exact decimals; rounding happens once per invoice line.

| Value | Stored as | Example |
|---|---|---|
| Overage rate | `NUMERIC(14,6)` (Python `Decimal`), paise per unit | `50.000000` = ₹0.50 per call |
| Line amount, invoice total | integer paise (`bigint`) | `100000` = ₹1,000.00 |

- The rate is a decimal because it can be a fraction of a paisa (0.2 paise per call).
- Each line is calculated exactly, then rounded once (`ROUND_HALF_UP`) to whole paise.
  - Example: 1,234 extra units × 0.2 paise = 246.8 → **247 paise**. Rounding per unit would give 0.
- The usage page uses the same pricing function as the invoice, so "cost so far" always matches the final bill.

### Cycle anchoring

**Decision:** a cycle starts on the customer's signup day each month. If a month has no such day, use its last day.

- Signup on the 31st: 31 Jan → 28 Feb → 31 Mar → 30 Apr.
- Each cycle is always computed as *signup date + N months*, never *previous cycle + 1 month*. That's what keeps the 31st from drifting to the 28th forever.

### Mid-cycle plan change (designed for, not implemented)

**Policy:** a plan change takes effect immediately; the cycle is split at the change.

- Usage before the change is priced on the old plan, usage after it on the new plan.
- Each part gets a share of its plan's allowance, by whole days, rounded down (so a partial day is never counted twice).
- The invoice shows one line per meter per plan period, each with its own dates, allowance and rate, so every number stays explainable.
- Threshold alerts restart at the split.
- **Schema change needed:** a dated `customer_plans` table (`customer_id, plan_id, effective_from`) instead of the single `customers.plan_id`. Nothing else blocks it: `invoice_lines` already carries per-line dates and rates.

### API design

**Decision:** plain REST resources, one error shape, and a batch that never fails because of one bad event.

- **Resources:** `events/batch`, `customers/{id}/usage`, `customers/{id}/invoices`, `invoices/{id}`. The two actions that aren't CRUD (`cycles/close`, `admin/counters/rebuild`) are explicit POSTs.
- **Batch status codes:**
  - `200` every event accepted or duplicate
  - `207` at least one event rejected (same body shape, with a result per event)
  - `400` request body malformed · `413` more than 1,000 events
- **One bad event never fails the batch:** the other 999 are stored and the bad one is reported with a reason.
- **One error shape everywhere:** `{"error": {"code", "message", "details"?}}`, including the framework's own 404/405.
- **Why validation is per event, not in the request schema:** a strict schema would reject the whole batch for one malformed item, which breaks the partial-success rule.

**Batch cap: 1,000 events per request.** Larger batches get `413` before any work. Keeps each transaction small and fast; the 500K load is simply 100 batches. (The CLI loader calls the service directly with 5,000-row batches.)

**Future timestamps: rejected beyond 5 minutes ahead.** Two servers' clocks are never exactly equal; a strict check would drop valid events from a clock a few seconds fast. Five minutes covers that without letting anyone pre-book next month's usage. Timestamps without a timezone are rejected rather than guessed.

**Simple API key.** One shared `X-API-Key` header on every route except `/health` and the webhook stub, as the assignment specifies.

**Polling, not push.** The dashboard refreshes usage, chart and alerts every 10 s. Simple, no connection state, and the reads are cheap indexed sums. WebSockets or SSE would replace it if sub-second freshness mattered.

**Force-close (demo only).** `{"force": true}` on the close endpoint, and the dashboard's "Close cycle" button, close the **current** cycle as of now so the demo can show an invoice without waiting a month. The invoice keeps the cycle's real dates; events that arrive afterwards for that cycle are treated as late.

---

## 5. API reference

Base path `/api/v1`, JSON in and out. Every route except `GET /health` and the webhook stub needs the `X-API-Key` header. Interactive docs with "Try it out": http://localhost:8000/docs.

| Method & path | Purpose | Success |
|---|---|---|
| `POST /events/batch` | Ingest up to 1,000 usage events | 200 all accepted/duplicate · 207 some rejected |
| `GET /customers` | List customers with plan and timezone | 200 |
| `GET /customers/{id}` | One customer plus their current cycle dates | 200 |
| `GET /customers/{id}/usage` | Current-cycle usage per meter: used, remaining, overage, cost so far | 200 |
| `GET /customers/{id}/usage/timeseries?meter=` | Daily usage for the chart | 200 |
| `GET /customers/{id}/notifications` | Threshold alerts for the current cycle (`?all=true` for every cycle) | 200 |
| `GET /customers/{id}/invoices` | Invoice list, newest first | 200 |
| `GET /invoices/{id}` | Invoice with its lines | 200 |
| `POST /customers/{id}/cycles/close` | Close a cycle into an invoice | 201 created · 200 already existed |
| `POST /cycles/close-due` | Close every customer's ended, un-invoiced cycle | 200 |
| `POST /admin/counters/rebuild` | Recompute `usage_counters` from raw events | 200 |
| `POST /webhook-receiver` | Stub that logs alert payloads (no key) | 200 |
| `GET /health` | Liveness (no key, no prefix) | 200 |

**Errors** always look like `{"error": {"code": "...", "message": "..."}}`:

| Status | `code` |
|---|---|
| 400 | `validation_error` (malformed body), `invalid_period_start` |
| 401 | `unauthorized` |
| 404 | `customer_not_found`, `invoice_not_found`, `unknown_meter` |
| 409 | `cycle_not_ended` |
| 413 | `batch_too_large` |

### `POST /events/batch`

Request:

```json
{"events": [
  {"event_id": "evt_1", "customer_id": "cus_asha", "meter": "api_calls", "quantity": 3, "occurred_at": "2026-03-15T10:00:00Z"},
  {"event_id": "evt_2", "customer_id": "cus_nobody", "meter": "api_calls", "quantity": 1, "occurred_at": "2026-03-15T10:00:00Z"}
]}
```

Response `207` (one event rejected):

```json
{"summary": {"received": 2, "accepted": 1, "duplicate": 0, "rejected": 1},
 "results": [
   {"event_id": "evt_1", "status": "accepted"},
   {"event_id": "evt_2", "status": "rejected", "error": {"code": "unknown_customer", "message": "unknown customer 'cus_nobody'"}}
 ]}
```

- `status` is `accepted`, `duplicate` or `rejected`; late accepted events also carry `"is_late": true`.
- Per-event rejection codes: `invalid_event`, `unknown_customer`, `unknown_meter`, `invalid_quantity`, `future_timestamp`, `late_event_too_old`.

### `GET /customers/{id}/usage`

```json
{"period": {"start": "2026-03-09T18:30:00Z", "end": "2026-04-09T18:30:00Z",
            "start_local": "2026-03-10T00:00:00+05:30", "end_local": "2026-04-10T00:00:00+05:30"},
 "currency": "INR",
 "meters": [
   {"meter": "api_calls", "display_name": "API calls", "unit": "call", "used": 12000, "allowance": 10000, "remaining": 0,
    "overage_units": 2000, "percent": 120.0, "state": "in_overage", "rate_minor": "50.000000", "cost_minor": 100000}
 ],
 "total_cost_minor": 100000}
```

- `state`: `within_allowance` (< 80 %), `approaching_limit` (80–99 %), `in_overage` (≥ 100 %).
- `*_minor` values are paise; `rate_minor` is a decimal string (paise per unit).

### `GET /invoices/{id}`

Invoice header plus `lines`. Every line carries what it needs to be explained: meter, period, quantity, allowance, overage units, rate and amount.

```json
{"id": "inv_3f9c2a7b1d04", "customer_id": "cus_asha", "period_start_local": "2026-02-10T00:00:00+05:30",
 "period_end_local": "2026-03-10T00:00:00+05:30", "currency": "INR", "total_minor": 125000, "status": "issued",
 "lines": [
   {"line_type": "usage", "meter": "api_calls", "quantity": 12000, "allowance": 10000, "overage_units": 2000,
    "rate_minor": "50.000000", "amount_minor": 100000,
    "description": "API calls: 12,000 call used, 10,000 included, 2,000 over allowance × ₹0.50 = ₹1,000.00", "adjusts_invoice_id": null},
   {"line_type": "adjustment", "meter": "api_calls", "quantity": 500, "allowance": 10000, "overage_units": 500,
    "rate_minor": "50.000000", "amount_minor": 25000,
    "description": "Late usage for 10 Jan – 09 Feb 2026 (received after invoice inv_9a1b2c3d4e5f)", "adjusts_invoice_id": "inv_9a1b2c3d4e5f"}
 ]}
```

- `line_type` is `usage` or `adjustment`; an adjustment points to the earlier invoice it corrects.

### `POST /customers/{id}/cycles/close`

Body, all optional: `{"period_start": "<UTC cycle start>", "force": false}`

- No body: closes the most recently ended cycle.
- `period_start`: closes that specific cycle.
- `force: true` (demo only): closes the current, still-running cycle as of now.
- `201` with the new invoice; `200` with the existing one if that cycle was already closed; `409 cycle_not_ended` if the cycle is still running and `force` is not set.

### Webhook payload

What the notifier POSTs to `WEBHOOK_URL` for each threshold crossing:

```json
{"customer_id": "cus_asha", "meter": "api_calls", "threshold": 80, "usage": 8120, "allowance": 10000,
 "period_start": "2026-03-09T18:30:00+00:00", "fired_at": "2026-03-20T09:12:44+00:00"}
```

---

## 6. Testing

```sh
docker compose run --rm -e TEST_DATABASE_URL=postgresql+psycopg://billing:billing@db:5432/billing_test api pytest --cov=app --cov-report=term-missing
```

One command runs both suites: **76 tests pass in ~20 s, 80 % total coverage** (core logic 93–100 %; the CLI and the notifier loop are the uncovered parts).

- **Unit tests** (`backend/tests/unit`): pure billing rules, no database.
- **Integration tests** (`backend/tests/integration`): real Postgres (`billing_test`), tables wiped and re-seeded before every test. Skipped automatically if `TEST_DATABASE_URL` is not set.

**What the assignment asked for, and where it's proven**

| Requirement | Test |
|---|---|
| Rating | [`test_rating.py`](backend/tests/unit/test_rating.py), [`test_money.py`](backend/tests/unit/test_money.py): overage-only pricing, 1,234 × 0.2 paise → 247 (rounded once) |
| Threshold deduplication | [`test_thresholds_db.py`](backend/tests/integration/test_thresholds_db.py): 50/80/100 fire exactly once across five batches plus a replay |
| Idempotency | [`test_ingest.py`](backend/tests/integration/test_ingest.py): **`test_reingesting_the_same_batch_does_not_move_the_numbers`**; in-batch duplicates; retry after partial delivery |
| Billing-period boundary in a non-UTC timezone | [`test_cycles.py`](backend/tests/unit/test_cycles.py): **Kolkata event at `2026-02-09T20:00Z` lands in the cycle starting `18:30Z`**; 31 Jan → 28 Feb → 31 Mar without drift; New York DST months |
| Validation | [`test_validation.py`](backend/tests/unit/test_validation.py): the four required rejections, future tolerance edge, late vs too-old |
| Invoicing | [`test_invoicing.py`](backend/tests/integration/test_invoicing.py): close twice → one invoice; explainable lines; late event → ₹ adjustment on the next invoice, old invoice untouched; `close-due` once per customer |
| Rebuildable aggregates | [`test_counters.py`](backend/tests/integration/test_counters.py): rebuilt counters equal the live ones |

---

## 7. Out of scope / not built

Excluded by the assignment: payments, tax, multi-currency (everything is INR), dunning, a real notification provider, auth beyond one API key, hard usage limits, observability tooling, Kubernetes.

Also left out, by choice:

- Mid-cycle plan changes: designed in [§4](#mid-cycle-plan-change-designed-for-not-implemented), not built.
- Per-customer API keys and webhook URLs.
- A second notifier process (the locking query makes it safe; one is enough here).
- Frontend tests.

---

## 8. Demo video checklist

Steps used for the [recorded videos](#demo-videos). Requests go through http://localhost:8000/docs (**Authorize** with `dev-key`); results are checked at http://localhost:5173.

| Scene | Steps | Expected |
|---|---|---|
| 1. Idempotent ingestion | `POST /events/batch` with 3 events (quantity 1 each); send the identical body again | 1st: 200, 3 `accepted` · 2nd: 200, 3 `duplicate` · usage stays at 3 |
| 2. Thresholds fire once | Send quantities 7,900 → 200 → 2,000 → 500, new `event_id` each time | 79 %: 50 % alert · 81 %: 80 % alert (orange) · 101 %: 100 % alert (red) · 500 more: no new alert · each shows **Sent** |
| 3. Invoice generation | Send 12,000 calls dated in the previous cycle; `POST …/cycles/close` with `{}` twice | 1st: 201, ₹1,000 · 2nd: 200, same invoice id · invoice page explains the line |
| 4. Late event | Send 100 calls dated inside that closed cycle; press **Close cycle** in the dashboard | `accepted`, `is_late: true` · old invoice unchanged · new invoice has a ₹50 adjustment line pointing to the old one |

- `occurred_at` must be at or before the current time (more than 5 minutes ahead is rejected).
- Alerts fire once per customer per cycle: to re-record scene 2, use another customer or reset with `docker compose down -v`.

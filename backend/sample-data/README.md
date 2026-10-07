# Sample data

`events.jsonl.gz` **is** checked in (500,000 events, seed 42, ~15 MB gzip JSONL). `generate` is only needed to recreate it; `load` is the command to run:

```sh
docker compose run --rm api python -m app.cli generate --events 500000 --out sample-data/events.jsonl.gz --seed 42   # optional: recreate
docker compose run --rm api python -m app.cli load --file sample-data/events.jsonl.gz --batch-size 5000
```

`sample-data/` is mounted as a volume in `docker-compose.yml`, so the file persists on the host.

## What the generator produces

- One JSON object per line: `{"event_id", "customer_id", "meter", "quantity", "occurred_at"}`.
- `event_id = "evt_" + uuid4 hex`, drawn from a seeded RNG, so the same `--seed` always yields the same ids
  (timestamps depend on the moment you run it: the window is the last 75 days, covering at least two full cycles).
- Customers are weighted (`CUSTOMER_WEIGHTS` in `app/cli.py`) so that over a full cycle `cus_asha` ends far past
  100 % of its basic-plan `api_calls` allowance, `cus_noor` lands around 90 %, and the pro customers stay below
  100 %. That is what makes the 50/80/100 % threshold notifications show up for some customers and not others.
- Meters: ~99.9 % `api_calls` (quantity 1, occasionally 2–3), ~0.1 % `storage_gb` (quantity 1–5).
- ~2 % of lines are deliberate duplicates (the same `event_id` and payload re-emitted shortly after the original),
  so the loader reports them as `duplicate` and the numbers do not move.
- Out-of-order delivery: events are shuffled inside 6-hour windows, plus a handful of far-out-of-order swaps.
- Events never predate the customer's signup day.

The loader calls `app.services.ingest.ingest_batch` directly (same code path as `POST /api/v1/events/batch`,
without the 1000-event API cap) and prints `accepted / duplicate / rejected` counts and the elapsed time.

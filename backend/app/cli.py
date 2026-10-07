"""Operational commands: seed, generate, load, rebuild-counters, close-due."""

from __future__ import annotations

import argparse
import gzip
import json
import random
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.domain.cycles import period_start_utc
from app.services.counters import rebuild_counters
from app.services.ingest import ingest_batch
from app.services.invoicing import close_due
from app.services.seed import SEED_CUSTOMERS, seed

# Share of events per customer. Over a full cycle this puts basic-plan cus_asha well past 100 %
# of its 10K api_calls allowance, cus_noor around 90 %, and keeps the pro customers below 100 %.
CUSTOMER_WEIGHTS = {"cus_asha": 0.075, "cus_noor": 0.045, "cus_ravi": 0.48, "cus_lee": 0.375, "cus_kai": 0.025}
# Storage is metered in whole GB with tiny allowances, so storage events must be rare to stay
# plausible.
METER_WEIGHTS = {"api_calls": 0.999, "storage_gb": 0.001}
WINDOW_DAYS = 75
DUPLICATE_RATIO = 0.02
FAR_OUT_OF_ORDER_RATIO = 0.0005
SHUFFLE_WINDOW = timedelta(hours=6)
DUPLICATE_LOOKBACK = 2000
PROGRESS_EVERY_BATCHES = 10


def generate_events(total: int, seed_value: int, now: datetime) -> list[dict[str, Any]]:
    """Generate an out-of-order event stream with duplicates, deterministic for a seed and `now`.
    `occurred_at` values stay datetimes until written."""
    rng = random.Random(seed_value)
    window_start = now - timedelta(days=WINDOW_DAYS)
    window_end = now - timedelta(minutes=1)
    anchors = {customer.id: customer for customer in SEED_CUSTOMERS}
    earliest = {
        customer_id: max(window_start, period_start_utc(anchors[customer_id].signup_date, anchors[customer_id].timezone, 0))
        for customer_id in CUSTOMER_WEIGHTS
    }

    unique_count = int(total * (1 - DUPLICATE_RATIO))
    customer_ids = rng.choices(list(CUSTOMER_WEIGHTS), weights=list(CUSTOMER_WEIGHTS.values()), k=unique_count)
    meter_ids = rng.choices(list(METER_WEIGHTS), weights=list(METER_WEIGHTS.values()), k=unique_count)
    events: list[dict[str, Any]] = []
    for customer_id, meter_id in zip(customer_ids, meter_ids):
        start = earliest[customer_id]
        occurred = start + timedelta(seconds=rng.random() * (window_end - start).total_seconds())
        events.append(
            {
                "event_id": "evt_" + uuid.UUID(int=rng.getrandbits(128), version=4).hex,
                "customer_id": customer_id,
                "meter": meter_id,
                "quantity": _quantity(rng, meter_id),
                "occurred_at": occurred,
            }
        )
    events.sort(key=lambda event: event["occurred_at"])
    _shuffle_within_windows(rng, events)
    _swap_far_out_of_order(rng, events)
    return _with_duplicates(rng, events, total - unique_count)


def _quantity(rng: random.Random, meter_id: str) -> int:
    if meter_id == "api_calls":
        return 1 if rng.random() < 0.95 else rng.randint(2, 3)
    return rng.randint(1, 5)


def _shuffle_within_windows(rng: random.Random, events: list[dict[str, Any]]) -> None:
    start = 0
    while start < len(events):
        window_end = events[start]["occurred_at"] + SHUFFLE_WINDOW
        end = start
        while end < len(events) and events[end]["occurred_at"] < window_end:
            end += 1
        window = events[start:end]
        rng.shuffle(window)
        events[start:end] = window
        start = end


def _swap_far_out_of_order(rng: random.Random, events: list[dict[str, Any]]) -> None:
    size = len(events)
    for _ in range(int(size * FAR_OUT_OF_ORDER_RATIO)):
        i, j = rng.randrange(size), rng.randrange(size)
        events[i], events[j] = events[j], events[i]


def _with_duplicates(rng: random.Random, events: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """Re-emit `count` recently seen events (same event_id and payload), like client retries would."""
    if count <= 0 or len(events) < 2:
        return events
    positions = set(rng.sample(range(1, len(events)), min(count, len(events) - 1)))
    output: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        if index in positions:
            output.append(output[rng.randrange(max(0, len(output) - DUPLICATE_LOOKBACK), len(output))])
        output.append(event)
    return output


def write_jsonl_gz(events: list[dict[str, Any]], out: Path) -> None:
    """Write events as gzip JSONL with ISO 8601 timestamps."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps({**event, "occurred_at": event["occurred_at"].isoformat()}) + "\n")


def load_file(path: Path, batch_size: int) -> Counter:
    """Ingest a gzip JSONL file in batches and return aggregate counts."""
    totals: Counter = Counter()
    started = time.perf_counter()
    batches = 0
    batch: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh, SessionLocal() as db:
        for line in fh:
            batch.append(json.loads(line))
            if len(batch) >= batch_size:
                batches += 1
                _ingest(db, batch, totals, batches, started)
                batch = []
        if batch:
            batches += 1
            _ingest(db, batch, totals, batches, started)
    totals["elapsed_seconds"] = round(time.perf_counter() - started, 2)
    return totals


def _ingest(db: Session, batch: list[dict[str, Any]], totals: Counter, batch_number: int, started: float) -> None:
    result = ingest_batch(db, batch)
    totals["received"] += result.received
    totals["accepted"] += result.accepted
    totals["duplicate"] += result.duplicate
    totals["rejected"] += result.rejected
    totals["thresholds_fired"] += result.thresholds_fired
    if batch_number % PROGRESS_EVERY_BATCHES == 0:
        elapsed = time.perf_counter() - started
        print(
            f"batch {batch_number}: received={totals['received']} accepted={totals['accepted']} "
            f"duplicate={totals['duplicate']} rejected={totals['rejected']} ({elapsed:.1f}s)"
        )


def cmd_seed(_: argparse.Namespace) -> None:
    """Upsert plans, meters and the demo customers."""
    with SessionLocal() as db:
        counts = seed(db)
    print("seeded " + ", ".join(f"{table}={count}" for table, count in counts.items()))


def cmd_generate(args: argparse.Namespace) -> None:
    """Generate a deterministic event file."""
    started = time.perf_counter()
    events = generate_events(args.events, args.seed, datetime.now(timezone.utc))
    write_jsonl_gz(events, args.out)
    print(f"wrote {len(events)} events to {args.out} in {time.perf_counter() - started:.1f}s (seed={args.seed})")


def cmd_load(args: argparse.Namespace) -> None:
    """Ingest an event file and print the totals."""
    totals = load_file(args.file, args.batch_size)
    print(
        f"loaded {args.file}: received={totals['received']} accepted={totals['accepted']} "
        f"duplicate={totals['duplicate']} rejected={totals['rejected']} "
        f"thresholds_fired={totals['thresholds_fired']} elapsed={totals['elapsed_seconds']}s"
    )


def cmd_rebuild_counters(_: argparse.Namespace) -> None:
    """Recompute usage_counters from raw events."""
    with SessionLocal() as db:
        rows = rebuild_counters(db)
    print(f"rebuilt usage_counters: {rows} rows")


def cmd_close_due(_: argparse.Namespace) -> None:
    """Invoice every customer's most recently ended, un-invoiced cycle."""
    with SessionLocal() as db:
        closed = close_due(db, datetime.now(timezone.utc))
    for item in closed:
        print(f"closed {item.customer_id} period {item.period_start.isoformat()} -> {item.invoice_id}")
    print(f"closed {len(closed)} cycle(s)")


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse command tree."""
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="usage-billing operations")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("seed", help="upsert plans, meters and the demo customers")

    generate = sub.add_parser("generate", help="write a deterministic gzip JSONL event file")
    generate.add_argument("--events", type=int, default=500_000)
    generate.add_argument("--out", type=Path, default=Path("sample-data/events.jsonl.gz"))
    generate.add_argument("--seed", type=int, default=42)

    load = sub.add_parser("load", help="ingest a gzip JSONL file through services.ingest in batches")
    load.add_argument("--file", type=Path, required=True)
    load.add_argument("--batch-size", type=int, default=5000)

    sub.add_parser("rebuild-counters", help="recompute usage_counters from raw events")
    sub.add_parser("close-due", help="invoice every customer's most recently ended, un-invoiced cycle")
    return parser


COMMANDS = {
    "seed": cmd_seed,
    "generate": cmd_generate,
    "load": cmd_load,
    "rebuild-counters": cmd_rebuild_counters,
    "close-due": cmd_close_due,
}


def main(argv: list[str] | None = None) -> None:
    """Parse `argv` and dispatch to the matching command."""
    args = build_parser().parse_args(argv)
    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()

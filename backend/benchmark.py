"""Repeatable LOCAL SQLite benchmark; never touches the application's PostgreSQL data.

Run inside the backend container:
    python benchmark.py --rows 1000

Metrics include ORM/database overhead and will vary with hardware and load.
SQLite in-memory is NOT a replacement for PostgreSQL load testing.
"""
import argparse
import json
import time
from decimal import Decimal
from statistics import median

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.ingestion import persist_rows
from app.parsing import OfferData


def run_benchmark(n: int, repeats: int) -> dict:
    observations = []
    for _ in range(repeats):
        # Isolated in-memory database for each observation.
        engine = create_engine('sqlite+pysqlite:///:memory:')
        Base.metadata.create_all(engine)
        rows = [{"id": f"SKU-{idx:06d}", "name": f"Benchmark product {idx}",
                 "price": str(10 + idx % 97), "stock": str(idx % 500)}
                for idx in range(n)]

        def normalize_sample(row: dict) -> OfferData:
            return OfferData(external_id=row['id'], name=row['name'],
                             price_amount=Decimal(row['price']), currency='EUR',
                             stock=int(row['stock']))

        with Session(engine) as session:
            start = time.perf_counter()
            inserted = persist_rows(session, source_name='Benchmark',
                                    filename='generated', rows=rows,
                                    normalizer=normalize_sample,
                                    first_row_number=1)
            insert_seconds = time.perf_counter() - start
            start = time.perf_counter()
            unchanged = persist_rows(session, source_name='Benchmark',
                                     filename='generated_again', rows=rows,
                                     normalizer=normalize_sample,
                                     first_row_number=1)
            repeat_seconds = time.perf_counter() - start
            assert inserted.inserted == n and inserted.rejected == 0
            assert unchanged.unchanged == n and unchanged.inserted == 0
        engine.dispose()
        observations.append((insert_seconds, repeat_seconds))

    first = median(ob[0] for ob in observations)
    second = median(ob[1] for ob in observations)
    return {
        "engine": "SQLite in-memory (isolated)",
        "rows_per_run": n,
        "repetitions": repeats,
        "insert_seconds_median": round(first, 3),
        "insert_rows_per_second": round(n / first, 1),
        "idempotent_repeat_seconds_median": round(second, 3),
        "idempotent_repeat_rows_per_second": round(n / second, 1),
        "duplicate_offers_created": 0,
        "note": "Local measurement; NOT a PostgreSQL or production throughput claim",
    }


def main():
    parser = argparse.ArgumentParser(description='Benchmark isolated DataBridge ingestion')
    parser.add_argument('--rows', type=int, default=1000, help='Rows per import (1 to 20000)')
    parser.add_argument('--repeats', type=int, default=3, help='Runs (1 to 10)')
    args = parser.parse_args()
    if not 1 <= args.rows <= 20000 or not 1 <= args.repeats <= 10:
        parser.error('rows must be 1..20000 and repeats must be 1..10')
    print(json.dumps(run_benchmark(args.rows, args.repeats), indent=2))


if __name__ == '__main__':
    main()

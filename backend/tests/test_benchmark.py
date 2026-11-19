"""The documented benchmark must run against an isolated temporary DB."""
from benchmark import run_benchmark


def test_benchmark_is_repeatable_and_does_not_create_duplicates():
    results = run_benchmark(12, 2)
    assert results["engine"] == "SQLite in-memory (isolated)"
    assert results["rows_per_run"] == 12
    assert results["repetitions"] == 2
    assert results["duplicate_offers_created"] == 0
    assert results["insert_seconds_median"] >= 0
    assert results["idempotent_repeat_seconds_median"] >= 0

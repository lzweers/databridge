# Engineering case study — DataBridge

## Context and problem

Supplier information often arrives through incompatible CSV exports and HTTP APIs, using different field names and number formats. Importing such data directly risks inconsistent values, duplicates and a loss of traceability. DataBridge explores a reliable **local-first** way to normalize, validate and inspect these inputs before they become catalog entries.

**Goal:** build a working full-stack portfolio application whose engineering decisions are visible, testable and explainable — not just an attractive dashboard.

## Scope delivered

- React/TypeScript user interface with a consistent enterprise design.
- FastAPI API with CSV upload, schema mapping and a fixed external REST connector.
- Shared validation/ingestion service backed by PostgreSQL.
- Structured validation issues and source-row retention.
- Idempotent imports keyed by supplier and external identifier.
- Lineage events with before/after comparisons.
- Opt-in scheduling through a separate Python worker, with execution history and retries.
- Data-quality summaries, server-side catalog search/pagination and filtered CSV export.

The public repository demonstrates **synthetic CSV inputs and a mock product API**. It does not contain real customer or confidential supplier records.

## Selected engineering decisions

**1. One ingestion engine, multiple sources** — CSV and DummyJSON have different adapters but use the same persistence and audit path. This reduces duplicated business logic and makes a third connector easier to add.

**2. Preserve input as well as output** — `source_rows` retain original payloads, while `offer_events` document the decision applied to each accepted row. This supports debugging and audit explanations.

**3. Model repeatability explicitly** — `(source_name, external_id)` is unique. Re-importing an unchanged offer records an unchanged event instead of adding a duplicate catalog record.

**4. Separate HTTP from scheduled work** — a dedicated worker executes due jobs and persists execution state. A slow or failed external request does not depend on the user's browser.

**5. Search at the database layer** — filtering and pagination run against the complete catalog rather than a client-side slice of 100 offers.

**6. Treat untrusted data cautiously** — enforce upload limits, use an allowlisted API URL, keep unknown currencies unknown, and escape spreadsheet-formula-looking text on CSV export.

## Verification evidence

- **Backend tests:** 30 passing tests on an isolated SQLite test database when the portfolio documentation was prepared. Tests cover ingestion and duplicate handling, connector failures, schema upgrades, lineage, scheduling, CORS, analytics and catalog/export behavior.
- **Frontend build:** validated locally during development; rerun `docker compose run --rm frontend npm run build` after final UI changes.
- **Benchmark:** on a local run with 1,000 synthetic records and three repetitions, an in-memory SQLite test measured median **0.709 s / 1,411 rows/s** for initial ingestion and **0.577 s / 1,733.5 rows/s** for identical re-ingestion; **0 duplicate offers** were created in that test.

**Measurement limits:** no recorded hardware profile; benchmark excludes production PostgreSQL, HTTP upload, external network, concurrent users and cloud infrastructure. It is evidence for comparing local code changes, not a capacity guarantee.

## Reliability incident and lesson

During hardening, a test fixture was found to depend on database configuration loaded before the intended SQLite test override. The test could therefore affect the local PostgreSQL volume. The resulting table loss was recovered as a new demo dataset after the original volume had been backed up.

**Corrective action:** test initialization now forces SQLite before application imports and refuses a non-SQLite engine. The incident illustrates why test isolation, data backups, and explicit verification matter more than a green test count on its own.

## Remaining production gaps

Authentication/authorization, tenant separation, real supplier contracts, managed secrets, migration tooling, resilient distributed job processing, observability and production deployment/security review are intentionally out of scope. The repository should be run locally, not exposed to untrusted internet users as-is.

## How to present the project

Demonstrate: import a deliberately malformed CSV → inspect rejected rows → import API data → repeat the import without duplicates → change a sample offer → trace the event → show worker execution status → examine server-side catalog filtering and export.

Rather than claiming "enterprise-ready", explain the tradeoffs and show the source code/tests for the decisions above.

**Development workflow:** the software was iteratively built and reviewed with AI coding assistance, together with local testing, debugging and a documented safety fix. The maintainer should be prepared to explain the architecture and individual decisions in an interview.

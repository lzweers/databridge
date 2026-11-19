# DataBridge — 3–5 minute recruiter demo

Use the **actual running application** at `http://localhost:5173` with demo records. Do not present static design concepts as screenshots of implemented features.

## Before recording

- Start Docker: `docker compose up -d --build`.
- Confirm `http://localhost:8000/api/health` returns `{"status":"ok"}`.
- Disable the five-minute automation unless the demo explicitly focuses on the worker.
- Use only `demo-data/lieferant_a.csv`, `demo-data/lieferant_a_update.csv` and DummyJSON demo products.
- Hide personal notifications, desktop paths, credentials and browser tabs.

## Suggested flow

1. **Problem (20 sec):** Supplier CSV/API fields are inconsistent; imported data must be reliable and auditable.
2. **CSV ingestion (45 sec):** Preview and map CSV columns; show accepted vs rejected rows and reasons.
3. **API ingestion (30 sec):** Open DummyJSON connector and show the external JSON preview and normalized offers. Explain that the API's currency is intentionally unknown.
4. **Idempotency + lineage (60 sec):** Re-import the same CSV with the same source name; explain why unchanged rows do not create duplicate offers. Then import the provided update file and inspect before/after history.
5. **Catalog & quality (45 sec):** Search the catalog, filter by source and export only the filtered results. Open the data-quality dashboard.
6. **Engineering (45 sec):** Show the architecture diagram, the isolated tests and an execution log from the background worker.

## Screenshots to capture from the actual app

Save your own current-screen captures in `docs/screenshots/` (create the folder). Suggested names: `dashboard.png`, `csv-import.png`, `quality-analytics.png`, `catalog.png`, `lineage.png`.

Crop out Windows paths and other unrelated UI. Images should represent the **real implemented interface**, not generated concept art. Add them to the README once captured.

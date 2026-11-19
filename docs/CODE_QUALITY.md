# DataBridge v0.5.1 — Engineering Quality Check

This update intentionally adds **no new UI features**. Its purpose is to make the already working DataBridge MVP reproducible, testable and safer as a **local-only** portfolio demo.

## Concrete fixes

1. **Benchmark inside the image:** `backend/Dockerfile` now has `COPY benchmark.py ./benchmark.py`. Therefore `docker compose run --rm backend python benchmark.py --rows 1000 --repeats 3` works without a PowerShell bind mount. The file must be included in the image built with `docker compose up --build`.
2. **Local-only ports:** `compose.yaml` publishes `127.0.0.1:5173` and `127.0.0.1:8000` on the host instead of listening on all host interfaces. The services can still communicate inside Docker's network. This is a safety measure, **not authentication**.
3. **Docker build hygiene:** `.dockerignore` files exclude transient build output, local databases, `.env` files and `node_modules` from Docker build context.
4. **Benchmark regression:** `backend/tests/test_benchmark.py` asserts that test imports and idempotent repeats run without creating duplicate offers. The benchmark uses only an in-memory SQLite database.
5. **Continuous integration:** `.github/workflows/backend-tests.yml` now runs Python tests, Python compilation, a tiny benchmark smoke test, a TypeScript/Vite build, and a backend Docker image smoke test. CI starts after pushing to GitHub, not automatically by downloading this ZIP.

## Check on Windows (PowerShell in VS Code)

> Before changing files: deactivate your 5-minute pipeline in the application and stop `docker compose up` with Ctrl+C. Back up your own changes, because the update overwrites files with the same names.

```powershell
Expand-Archive -Path "$env:USERPROFILE\Downloads\databridge-v051-update.zip" -DestinationPath "." -Force
docker compose up --build
```

In a **second VS Code terminal**, inside the `databridge-starter` folder:

```powershell
docker compose run --rm backend pytest -q
docker compose run --rm backend python benchmark.py --rows 1000 --repeats 3
docker compose run --rm frontend npm run build
```

Expected: 22 backend tests pass; benchmark prints JSON and includes `"duplicate_offers_created": 0`; frontend builds without TypeScript errors. Your actual timing numbers will differ. **Do not** use `docker compose down -v` — that removes the PostgreSQL volume.

## Quality limits / honest portfolio claims

- The Python tests and benchmark smoke test were executed against the extracted v0.5.1 code: 22 tests passed. A full Docker build and frontend npm build were **not** executed in the authoring environment. Please check both locally.
- The benchmark is SQLite in-memory, not PostgreSQL, cloud or multi-user load testing.
- The UI contains no accounts or authentication; the API and update operations are still **not safe for public deployment**. Binding host ports to localhost narrows access but does not supply access control.
- Hard-coded local database credentials are **development-only** and must not be reused in production.
- The MVP uses `create_all` plus a narrow legacy-schema upgrader; production-style schema migrations, authorization, upload hardening, CSRF considerations, rate limits, secrets management, and deployment architecture remain future work.
- Dependencies are bounded but not fully locked. Before production or reproducible release builds, check a Python lock strategy and commit a `package-lock.json` to use `npm ci`.

## Three portfolio-ready proof points

- **Reliability:** Re-importing the same valid offers does not add duplicates. Test: `backend/tests/test_benchmark.py` and ingestion test suite.
- **CORS bugfix:** Browser `PUT` to the schedule endpoint passes a CORS preflight; this is covered in `backend/tests/test_quality.py`.
- **Reproducibility:** A single documented Docker command starts the local stack; CI checks both source code and the packaging of the benchmark executable.

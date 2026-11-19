# Security and operational limitations

DataBridge is a local-first development and portfolio demonstration, not a production service.

## Implemented safeguards

- HTTP port bindings in the provided Docker Compose file are restricted to `127.0.0.1`.
- The CSV endpoint accepts `.csv` files with an upload-size cap of 5 MiB and server-side parsing/validation.
- The demonstration connector uses a fixed HTTPS endpoint; users cannot instruct the server to fetch arbitrary URLs.
- CSV export neutralizes common leading characters that can trigger spreadsheet formulas.
- Backend tests use an isolated SQLite database and a guard against accidental non-SQLite test execution.
- Secrets, backups and local database files are excluded from Git by `.gitignore` (check for already-tracked exceptions).

## Not yet implemented

- Authentication, authorization, tenant isolation or secure multi-user deployment.
- Secret management for real supplier credentials or encrypted storage for confidential records.
- A hardened production network boundary, rate limiting, complete audit access policy, or automated vulnerability scan.
- Production-grade migrations, distributed scheduler guarantees or production monitoring.

**Do not expose the current API publicly and do not ingest confidential business data.** The hardcoded `localdev` password is appropriate only for throwaway local development and must not be reused in a deployment.

## Responsible disclosure

If a security issue is found during review, describe the reproduction steps privately to the repository maintainer rather than posting sensitive payloads in a public issue.

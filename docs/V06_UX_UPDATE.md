# DataBridge v0.6 — UX / Demo Flow Update

## Compatibility

Overlay for the DataBridge v0.5.2 hotfix state (the frontend files are unchanged between v0.5.1 and the hotfix). No backend, Docker configuration, database migration, or volume changes.

## Changes

- **Never show a legitimate count of zero on API failure:** overview cards, import history and catalog now distinguish `loading`, `ready`, and `error`.
- **Retry:** connection failures display actionable backend help and a retry control.
- **Demo tour:** the overview shows three guided steps derived from actual import history: CSV import, DummyJSON import, and at least one updated row. No fake progress data.
- **Import history:** status filter applies to the currently visible 50 rows; pagination now displays page counts.
- **CSV input validation:** early feedback for non-CSV files and files above 5 MiB (server validation remains responsible for security).

## Upgrade on Windows (PowerShell in project root)

1. Make sure your working directory is `databridge-starter` (contains `compose.yaml`).
2. Extract the ZIP into that directory, overwriting only `frontend/src/App.tsx` and `frontend/src/style.css` (plus this document):

   ```powershell
   Expand-Archive -Path "$env:USERPROFILE\Downloads\databridge-v06-ux-update.zip" -DestinationPath "." -Force
   ```
3. Build and start **only the frontend** (existing backend/db can remain running):

   ```powershell
   docker compose up -d --build frontend
   ```
4. Open http://localhost:5173 and hard refresh (Ctrl+F5).
5. Validate frontend compilation:

   ```powershell
   docker compose run --rm frontend npm run build
   ```

## Smoke tests

- Existing imported data still visible in overview (e.g. 28 offers / 3 runs if using the previous example data).
- Three demo cards show status based on saved import runs (not hardcoded).
- Open Import History > choose an import > filter to 'Abgelehnt' and return to 'Alle Status'. Note the page count.
- Optional: pick a deliberately oversized CSV file; the upload should be rejected by the frontend before sending a request.
- When the API is temporarily unavailable, the UI should show 'Daten nicht verfügbar' and a retry button rather than zeros. Do not stop/delete the database to test this.

## Test status

The TSX was syntax-parsed and transpiled with TypeScript. Complete npm/Vite build could not be run here because the package registry dependencies were unavailable in the execution environment. Perform the Docker frontend build above on your machine before publication.

## Important safety note

Do NOT use `docker compose down -v`. This update contains **no changes to backend tests**. Keep the earlier v0.5.2 safety hotfix installed; do not overwrite it with older backend files.

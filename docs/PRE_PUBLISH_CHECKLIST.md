# DataBridge — GitHub publication checklist (Windows / VS Code)

## 1. Keep local information out of Git

The `.gitignore` excludes database files, recovery archives, `.env` files, private keys, build outputs, logs and dependencies.

**Important:** `.gitignore` blocks *newly untracked* files. It does not remove something already tracked. Run `scripts/prepublish-check.ps1` after staging to inspect Git's index.

- [ ] `databridge-rescue-backup.tar.gz` is NOT staged or tracked.
- [ ] No real `.env`, passwords, access tokens, private keys, customer files or private datasets are staged.
- [ ] Only the **synthetic** CSV samples in `demo-data/` are included.
- [ ] No `.git/`, `node_modules/`, `dist/`, `*.db`, `*.zip` or backups are added.
- [ ] `compose.yaml` is documented as local development only (the `localdev` password is not a deployable credential).

## 2. Validate the actual version

```powershell
docker compose up -d --build
docker compose run --rm backend python -m pytest -q
docker compose run --rm frontend npm run build
docker compose run --rm backend python benchmark.py --rows 1000 --repeats 3
```

Save your actual results. Do **not** run a test suite if the SQLite isolation guard in `backend/tests/conftest.py` is missing or has been replaced by an earlier version.

- [ ] Dashboard, imports, catalog filters, CSV export and lineage work.
- [ ] API-Connector handles a successful fetch; failed fetches show a useful error.
- [ ] Automation is disabled before capturing the demo.
- [ ] Recent screenshots are from the *running* green/white Corporate UI.

## 3. Prepare Git

Open PowerShell in the project root (`databridge-starter`, where `compose.yaml` is located):

```powershell
git --version
git init
git branch -M main
git add .
powershell -ExecutionPolicy Bypass -File .\scripts\prepublish-check.ps1
git status --short
```

If the audit reports a tracked backup file, remove **only from Git's index** (keeps the local file):

```powershell
git rm --cached -- databridge-rescue-backup.tar.gz
```

Run the audit again. Inspect staged files before committing:

```powershell
git diff --cached --stat
git commit -m "Prepare DataBridge portfolio release"
```

## 4. Publish to GitHub

Create a **new empty** repository `databridge` on GitHub. Do not generate a remote README or `.gitignore`, as the local project already has both. Set repository visibility to **Public** only once the audit is clean.

In your VS Code PowerShell terminal, replace `<YOUR_GITHUB_USERNAME>` with your username:

```powershell
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/databridge.git
git push -u origin main
```

If `origin` already exists, inspect `git remote -v` rather than blindly overriding it. Authentication should be handled by GitHub's normal browser / credential manager flow; never paste tokens into chat or the repository.

## 5. Make it recruiter-friendly

- [ ] Add two or three real screenshots to `assets/screenshots/` and link them from the README.
- [ ] Set GitHub About description, e.g. `Local-first data operations app: CSV/API ingestion, validation, lineage, job scheduling and quality analytics.`
- [ ] Set topics: `react`, `typescript`, `fastapi`, `python`, `postgresql`, `etl`, `data-quality`, `docker`.
- [ ] Check the **Actions** tab; the included workflow should test backend, frontend build and Docker packaging.
- [ ] Decide whether to add an open-source license. Without a license, others can inspect public code but do not automatically receive broad reuse rights.
- [ ] Link the repo from your résumé and portfolio with a short architecture/problem statement.

## Security note

**Public source code is different from a public running instance.** The current API has no authentication and must remain accessible only on local development ports. Never publish it unchanged as a public hosted service.

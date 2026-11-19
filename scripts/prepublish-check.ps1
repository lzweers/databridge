# Read-only Git index check; this script never deletes files or changes Git state.
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath ".git")) {
    Write-Host "Git repository not initialized. Run 'git init', then 'git add .' first." -ForegroundColor Yellow
    exit 1
}

$files = @(git ls-files --cached)
if ($LASTEXITCODE -ne 0) {
    Write-Host "Could not read Git index." -ForegroundColor Red
    exit 1
}

if ($files.Count -eq 0) {
    Write-Host "Nothing staged or tracked yet. Run 'git add .' first." -ForegroundColor Yellow
    exit 1
}

$pattern = '(?i)(^|/)(\.env(?:\..*)?|credentials\.json|secrets\.json|[^/]+\.(?:zip|tar|tgz|gz|dump|backup|bak|sqlite|sqlite3|db|pem|key|p12|pfx))$'
$bad = @($files | Where-Object { ($_ -match $pattern) -and ($_ -notmatch '(?i)(^|/)\.env\.example$') })

if ($bad.Count -gt 0) {
    Write-Host "STOP: sensitive / local files are tracked by Git:" -ForegroundColor Red
    $bad | ForEach-Object { Write-Host " - $_" }
    Write-Host "To unstage an existing tracked file without deleting the local copy: git rm --cached -- <file>" -ForegroundColor Yellow
    exit 1
}

Write-Host "Pre-publication index check OK: $($files.Count) tracked/staged paths; no known archive, secret or database file names." -ForegroundColor Green
Write-Host "Still manually inspect 'git status --short' and 'git diff --cached --stat'. A filename check cannot detect secrets hidden inside ordinary source files." -ForegroundColor Yellow

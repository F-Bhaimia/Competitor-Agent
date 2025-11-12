# automation\nightly_update.ps1
# Run with: powershell.exe -ExecutionPolicy Bypass -File "C:\path\to\competitor_news_monitor\automation\nightly_update.ps1"

$ErrorActionPreference = "Stop"

# --- CONFIG ---
$ProjectDir = "C:\Users\fbhaimia\OneDrive - MemberSolutions\Desktop\competitor_news_monitor"
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"   # venv python
$LogDir     = Join-Path $ProjectDir "logs"
$SinceFile  = Join-Path $ProjectDir "data\.last_run.txt"
$LockName   = "Global\CompetitorNewsNightlyLock"  # Windows-wide mutex name
$EnvFile    = Join-Path $ProjectDir ".env"        # optional .env

# --- Ensure folders/logging ---
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$ts = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH-mm-ssZ")
$LogFile = Join-Path $LogDir "run_$ts.log"
"=== Nightly update started @ $((Get-Date).ToUniversalTime().ToString('u')) ===" | Out-File -FilePath $LogFile -Append

# --- Load .env if present (simple KEY=VALUE lines) ---
if (Test-Path $EnvFile) {
  Get-Content $EnvFile | ForEach-Object {
    if ($_ -match "^\s*#") { return } # skip comments
    if ($_ -match "^\s*$") { return } # skip blanks
    $parts = $_ -split "=", 2
    if ($parts.Count -eq 2) {
      $k = $parts[0].Trim()
      $v = $parts[1].Trim()
      if ($k -and $v) { [System.Environment]::SetEnvironmentVariable($k, $v, "Process") }
    }
  }
}

# --- No-overlap lock via Mutex ---
Add-Type -AssemblyName System.Core | Out-Null
$hasHandle = $false
$mutex = New-Object System.Threading.Mutex($true, $LockName, [ref]$createdNew)
try {
  $hasHandle = $mutex.WaitOne(0, $false)
  if (-not $hasHandle) {
    "Another run appears to be active. Exiting." | Out-File -FilePath $LogFile -Append
    exit 0
  }

  # --- Check venv python ---
  if (-not (Test-Path $VenvPython)) {
    "ERROR: venv python not found at $VenvPython" | Out-File -FilePath $LogFile -Append
    exit 1
  }

  Set-Location $ProjectDir

  # --- Determine SINCE ---
  $since = "2025-01-01T00:00:00Z"
  if (Test-Path $SinceFile) {
    $since = (Get-Content $SinceFile -ErrorAction SilentlyContinue | Select-Object -Last 1)
    if (-not $since) { $since = "2025-01-01T00:00:00Z" }
  }

  # === 1) (Optional) FETCH new items ===
  # When you add your fetcher, uncomment one of these and adjust module/args:
  # & $VenvPython -m jobs.fetch_google_news --since $since *>> $LogFile
  # & $VenvPython -m jobs.fetch_sources --since $since *>> $LogFile

  # === 2) ENRICH any rows missing summary/category/impact ===
  & $VenvPython -m jobs.enrich_updates *>> $LogFile

  # === 3) Update last-run marker ===
  (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ") | Out-File -FilePath $SinceFile

  "=== Nightly update completed @ $((Get-Date).ToUniversalTime().ToString('u')) ===" | Out-File -FilePath $LogFile -Append
}
catch {
  "ERROR: $($_.Exception.Message)" | Out-File -FilePath $LogFile -Append
  exit 1
}
finally {
  if ($hasHandle -and $mutex) { $mutex.ReleaseMutex() | Out-Null }
  if ($mutex) { $mutex.Dispose() }
}

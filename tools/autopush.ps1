# Sites of Grace - auto-push watcher
#
# Runs every few minutes from Task Scheduler. If the working tree has been
# quiet for a full cycle, it commits everything and pushes to main, which
# triggers the DigitalOcean autodeploy.
#
# Every external command runs with a timeout. Nothing here can hang forever:
# a hidden window plus a program waiting on input would otherwise stall the
# watcher and block every run after it.
#
# It refuses to push when something looks wrong, and when it refuses it drops
# AUTOPUSH-BLOCKED.txt in the repo root so the reason is visible without
# digging through the log.
#
# Pause it any time by creating an empty file named .autopush-pause in the
# repo root. Delete that file to resume.

$ErrorActionPreference = 'Continue'

$Repo       = Split-Path -Parent $PSScriptRoot
$LogFile    = Join-Path $PSScriptRoot 'autopush.log'
$StateFile  = Join-Path $PSScriptRoot '.autopush-state'
$PauseFile  = Join-Path $Repo '.autopush-pause'
$BlockFile  = Join-Path $Repo 'AUTOPUSH-BLOCKED.txt'
$Branch     = 'main'
$MaxFileMB  = 5

Set-Location $Repo

function Write-Log {
    param([string]$Level, [string]$Message)
    $line = "{0}  {1,-7} {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Message
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# Runs an external program with a hard timeout. Returns ExitCode, Output and
# TimedOut. A program that stalls gets killed instead of stalling the watcher.
#
# This drives System.Diagnostics.Process directly rather than using
# Start-Process -PassThru, whose .ExitCode comes back $null on Windows
# PowerShell 5.1 -- which reads as "failed" and made every run bail out.
# The two output streams are drained asynchronously so a chatty command
# cannot deadlock on a full pipe buffer.
function Invoke-Ext {
    param(
        [string]$File,
        [string[]]$Arguments,
        [int]$TimeoutSec = 120
    )
    try {
        $quoted = $Arguments | ForEach-Object {
            if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
        }
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName               = $File
        $psi.Arguments              = ($quoted -join ' ')
        $psi.WorkingDirectory       = $Repo
        $psi.UseShellExecute        = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError  = $true
        $psi.RedirectStandardInput  = $true
        $psi.CreateNoWindow         = $true

        $proc = [System.Diagnostics.Process]::Start($psi)
        # Close stdin so anything that decides to prompt gets EOF and gives up
        # rather than waiting on a keyboard that isn't there.
        $proc.StandardInput.Close()
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $errTask = $proc.StandardError.ReadToEndAsync()

        if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
            try { $proc.Kill() } catch { }
            Start-Sleep -Milliseconds 300
            return [pscustomobject]@{ ExitCode = -1; Output = ''; TimedOut = $true }
        }
        $proc.WaitForExit()
        $combined = (($outTask.Result + "`n" + $errTask.Result).Trim())
        return [pscustomobject]@{ ExitCode = $proc.ExitCode; Output = $combined; TimedOut = $false }
    } catch {
        return [pscustomobject]@{ ExitCode = -2; Output = $_.Exception.Message; TimedOut = $false }
    }
}

function Invoke-Git {
    param([string[]]$Arguments, [int]$TimeoutSec = 120)
    return Invoke-Ext -File 'git' -Arguments $Arguments -TimeoutSec $TimeoutSec
}

function Block-Push {
    param([string]$Reason, [string]$Detail = '')
    Write-Log 'BLOCKED' $Reason
    if ($Detail) { Write-Log 'BLOCKED' ($Detail -replace "`r?`n", ' | ') }
    $body = @(
        "Auto-push stopped and did NOT push anything.",
        "",
        "When: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        "Why:  $Reason",
        ""
    )
    if ($Detail) { $body += $Detail; $body += "" }
    $body += @(
        "Your changes are safe on disk. Nothing was lost.",
        "Fix the problem above, or paste this file to Claude and ask what it means.",
        "This file disappears on its own once a push succeeds."
    )
    Set-Content -Path $BlockFile -Value ($body -join [Environment]::NewLine) -Encoding UTF8
    Invoke-Git @('reset') | Out-Null
    exit 1
}

if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt 1MB)) {
    Move-Item -Path $LogFile -Destination "$LogFile.old" -Force
}

if (Test-Path $PauseFile) {
    Write-Log 'PAUSED' '.autopush-pause is present - skipping this run.'
    exit 0
}

# --- Is there anything to do? -------------------------------------------------

$r = Invoke-Git @('status', '--porcelain') 30
if ($r.TimedOut)      { Write-Log 'ERROR' 'git status timed out.'; exit 1 }
if ($r.ExitCode -ne 0) { Write-Log 'ERROR' "git status failed: $($r.Output)"; exit 1 }

$status = @($r.Output -split "`r?`n" | Where-Object { $_.Trim() -ne '' })
if ($status.Count -eq 0) {
    if (Test-Path $StateFile) { Remove-Item $StateFile -Force }
    exit 0
}

# --- Debounce: only ship changes that have stopped moving ---------------------

$fingerprint = ($status -join "`n")
$previous = if (Test-Path $StateFile) { Get-Content $StateFile -Raw } else { '' }
if ($null -eq $previous) { $previous = '' }

if ($fingerprint -ne $previous.TrimEnd()) {
    Set-Content -Path $StateFile -Value $fingerprint -Encoding UTF8
    Write-Log 'WAIT' "$($status.Count) file(s) changed - waiting one cycle to be sure they've settled."
    exit 0
}

Write-Log 'START' "$($status.Count) file(s) have settled. Checking them before pushing."

# --- Stage, then inspect what we're about to ship -----------------------------

$r = Invoke-Git @('add', '-A') 120
if ($r.TimedOut)       { Block-Push 'git add timed out after 2 minutes.' }
if ($r.ExitCode -ne 0) { Block-Push 'git add failed.' $r.Output }

$r = Invoke-Git @('diff', '--cached', '--name-only') 60
if ($r.ExitCode -ne 0) { Block-Push 'Could not list the staged files.' $r.Output }
$staged = @($r.Output -split "`r?`n" | Where-Object { $_.Trim() -ne '' })

if ($staged.Count -eq 0) {
    Write-Log 'INFO' 'Nothing staged after git add (all changes are gitignored). Skipping.'
    if (Test-Path $StateFile) { Remove-Item $StateFile -Force }
    exit 0
}
Write-Log 'STEP' "Staged $($staged.Count) file(s). Running safety checks."

# Blocker 1: files that should never reach a git remote.
$forbidden = @(
    '\.dump$', '\.sql$', '\.env$', '(^|/)\.env\.', '\.pem$', '\.pfx$', '\.p12$',
    '(^|/)id_rsa', '(^|/)db\.sqlite3$', '(^|/)local\.py$', '\.bak$'
)
foreach ($file in $staged) {
    foreach ($pattern in $forbidden) {
        if ($file -match $pattern) {
            Block-Push "A file that must not be published was staged: $file" `
                       "Add it to .gitignore, then delete AUTOPUSH-BLOCKED.txt."
        }
    }
}

# Blocker 2: anything unexpectedly large.
foreach ($file in $staged) {
    $full = Join-Path $Repo $file
    if (Test-Path $full -PathType Leaf) {
        $mb = [math]::Round((Get-Item $full).Length / 1MB, 1)
        if ($mb -gt $MaxFileMB) {
            Block-Push "$file is ${mb} MB, over the ${MaxFileMB} MB limit." `
                       "If it belongs in the repo, raise MaxFileMB in tools/autopush.ps1."
        }
    }
}

# Blocker 3: credentials pasted into a file. This script excludes itself, since
# the patterns below would match it.
$secretPatterns = @(
    'dop_v1_[0-9a-f]{64}',
    'AKIA[0-9A-Z]{16}',
    'ghp_[A-Za-z0-9]{36}',
    'xox[baprs]-[0-9A-Za-z-]{10,}',
    '-----BEGIN [A-Z ]*PRIVATE KEY-----'
)
$textExtensions = @('.py', '.html', '.css', '.js', '.md', '.txt', '.json', '.yml', '.yaml', '.cfg', '.ini', '.toml', '.bat', '.ps1')
foreach ($file in $staged) {
    if ($file -like '*autopush.ps1') { continue }
    $full = Join-Path $Repo $file
    if (-not (Test-Path $full -PathType Leaf)) { continue }
    if ($textExtensions -notcontains [System.IO.Path]::GetExtension($file)) { continue }
    if ((Get-Item $full).Length -gt 1MB) { continue }
    $content = Get-Content $full -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }
    foreach ($pattern in $secretPatterns) {
        if ($content -match $pattern) {
            Block-Push "$file looks like it contains a live credential." `
                       "Remove the secret, put it in an environment variable, then delete AUTOPUSH-BLOCKED.txt."
        }
    }
}
Write-Log 'STEP' 'Safety checks passed. Running Django checks.'

# --- Does the app still work? -------------------------------------------------

$python = Join-Path $Repo 'venv\Scripts\python.exe'
if (Test-Path $python) {
    $r = Invoke-Ext -File $python -Arguments @('manage.py', 'check') -TimeoutSec 180
    if ($r.TimedOut) {
        Write-Log 'WARN' 'manage.py check did not finish in 3 minutes - skipping the Django checks.'
    } elseif ($r.ExitCode -ne 0) {
        Block-Push 'Django checks failed, so this was not pushed.' $r.Output
    } else {
        $r = Invoke-Ext -File $python -Arguments @('manage.py', 'makemigrations', '--check', '--dry-run') -TimeoutSec 180
        if ($r.TimedOut) {
            Write-Log 'WARN' 'makemigrations --check did not finish in 3 minutes - skipped.'
        } elseif ($r.ExitCode -ne 0) {
            Block-Push 'A model was changed without a matching migration.' `
                       ("Pushing this would break production on deploy. Run:`r`n" +
                        "    python manage.py makemigrations`r`n" +
                        "then delete AUTOPUSH-BLOCKED.txt.`r`n`r`n" + $r.Output)
        } else {
            Write-Log 'CHECK' 'Django checks passed, no migration drift.'
        }
    }
} else {
    Write-Log 'WARN' 'venv not found - skipped the Django checks for this push.'
}

# --- Commit -------------------------------------------------------------------

$summary = if ($staged.Count -le 3) { $staged -join ', ' } else { "$($staged[0]), $($staged[1]) and $($staged.Count - 2) more" }
$messageLines = @(
    "Auto-commit: $summary",
    "",
    "Committed by the auto-push watcher on $(Get-Date -Format 'yyyy-MM-dd HH:mm'),",
    "picking up changes made in a Claude session.",
    "",
    "Files:"
) + ($staged | ForEach-Object { "  $_" }) + @(
    "",
    "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
)
$msgFile = Join-Path $env:TEMP "autopush-msg-$PID.txt"
# UTF8 without a byte-order mark: Set-Content -Encoding UTF8 writes one on
# Windows PowerShell 5.1, and git puts it straight into the commit subject.
[System.IO.File]::WriteAllText(
    $msgFile,
    ($messageLines -join [Environment]::NewLine),
    (New-Object System.Text.UTF8Encoding($false)))

$before = (Invoke-Git @('rev-parse', '--short', 'HEAD') 30).Output
$r = Invoke-Git @('commit', '-F', $msgFile) 120
Remove-Item $msgFile -Force -ErrorAction SilentlyContinue
if ($r.TimedOut)       { Block-Push 'git commit timed out after 2 minutes.' }
if ($r.ExitCode -ne 0) { Block-Push 'git commit failed.' $r.Output }
$after = (Invoke-Git @('rev-parse', '--short', 'HEAD') 30).Output
Write-Log 'COMMIT' "$before -> $after  ($($staged.Count) file(s))"

# --- Push ---------------------------------------------------------------------

$r = Invoke-Git @('pull', '--rebase', 'origin', $Branch) 240
if ($r.TimedOut) {
    Invoke-Git @('rebase', '--abort') 60 | Out-Null
    Block-Push 'Fetching from GitHub timed out after 4 minutes.' `
               "Commit $after is saved locally. Check the network, then run tools\autopush-run.bat by hand."
}
if ($r.ExitCode -ne 0) {
    Invoke-Git @('rebase', '--abort') 60 | Out-Null
    Block-Push 'The remote has changes that conflict with these.' `
               ("Your commit $after is saved locally. Run 'git pull --rebase origin $Branch' and resolve it.`r`n`r`n" + $r.Output)
}

$r = Invoke-Git @('push', 'origin', $Branch) 240
if ($r.TimedOut) {
    Block-Push 'The push to GitHub timed out after 4 minutes.' `
               "This usually means git is waiting for a sign-in it cannot show, because the watcher runs with no window. Double-click tools\autopush-run.bat once and sign in when prompted."
}
if ($r.ExitCode -ne 0) {
    Block-Push 'The push to GitHub was rejected.' `
               ("Commit $after is saved locally, so nothing is lost.`r`n`r`n" + $r.Output)
}

Write-Log 'PUSHED' "$after -> origin/$Branch. DigitalOcean should be building now."

if (Test-Path $BlockFile)  { Remove-Item $BlockFile -Force }
if (Test-Path $StateFile)  { Remove-Item $StateFile -Force }
exit 0

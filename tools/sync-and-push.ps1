# One-time repair: bring this checkout up to date with GitHub, put the store
# changes on top of it, and push.
#
# Why this exists: this folder was six days behind GitHub, so the store work was
# written against older copies of .gitignore and home/models.py. Committing it
# as-is would collide with the homepage and section-nav commits already on
# main. This syncs first, then lays the store changes on the current files.
#
# It is safe to run twice. Once it has succeeded, the normal watcher takes over
# and you should not need this again.

$ErrorActionPreference = 'Continue'

$Repo    = Split-Path -Parent $PSScriptRoot
$Pending = Join-Path $PSScriptRoot 'pending'
$Branch  = 'main'
Set-Location $Repo

function Say { param([string]$Text) Write-Host $Text }
function Fail {
    param([string]$Text, [string]$Detail = '')
    Write-Host ''
    Write-Host '  STOPPED --------------------------------------------------' -ForegroundColor Red
    Write-Host "  $Text" -ForegroundColor Red
    if ($Detail) { Write-Host ''; Write-Host $Detail }
    Write-Host ''
    Write-Host '  Nothing was pushed. Your files are still on disk.'
    Write-Host '  Copy this window to Claude and it will tell you what to do.'
    Write-Host '  ----------------------------------------------------------' -ForegroundColor Red
    exit 1
}
$GitExe = (Get-Command git -CommandType Application -ErrorAction SilentlyContinue |
           Select-Object -First 1).Source
if (-not $GitExe) { Write-Host '  Git is not installed, or not on PATH.'; exit 1 }

# Call sites always pass one array, e.g. Invoke-G @('add','-A'). Passing the
# flags loose would let PowerShell mistake "-A" for a parameter name.
function Invoke-G {
    param([string[]]$Arguments)
    $output = & $GitExe @Arguments 2>&1 | Out-String
    return [pscustomobject]@{ Code = $LASTEXITCODE; Out = $output.Trim() }
}

Say ''
Say '=================================================================='
Say '  Sites of Grace - sync with GitHub and push the store changes'
Say '=================================================================='
Say ''

# --- 0. Stop anything the watcher left running -------------------------------

Say '  Stopping any watcher run that is still going...'
schtasks /End /TN "SitesOfGrace AutoPush" 2>&1 | Out-Null
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*autopush.ps1*' } |
    ForEach-Object {
        Say "    ending a stuck run (pid $($_.ProcessId))"
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
Remove-Item (Join-Path $PSScriptRoot '.autopush-state') -Force -ErrorAction SilentlyContinue

if (-not (Test-Path (Join-Path $Pending 'home_models.py'))) { Fail "Missing tools\pending\home_models.py - re-run this after Claude delivers it." }
if (-not (Test-Path (Join-Path $Pending 'gitignore.txt'))) { Fail "Missing tools\pending\gitignore.txt - re-run this after Claude delivers it." }

# --- 1. What does GitHub have? ------------------------------------------------

Say '  Fetching from GitHub...'
$r = Invoke-G @('fetch','origin')
if ($r.Code -ne 0) { Fail 'Could not reach GitHub.' $r.Out }

$head   = (Invoke-G @('rev-parse','--short','HEAD')).Out
$remote = (Invoke-G @('rev-parse','--short',"origin/$Branch")).Out
Say "    this folder: $head"
Say "    GitHub:      $remote"

$anc = Invoke-G @('merge-base','--is-ancestor','HEAD',"origin/$Branch")
if ($anc.Code -ne 0) {
    # The watcher already committed the store work on the old base. Undo just
    # that commit -- the files stay exactly as they are on disk -- so it can be
    # replayed on top of what GitHub has. Steven's own commits are never touched.
    $mb = (Invoke-G @('merge-base','HEAD',"origin/$Branch")).Out
    if (-not $mb) { Fail 'This folder and GitHub share no history.' 'That should not be possible - send this window to Claude.' }

    $subjects = @((Invoke-G @('log','--format=%s',"$mb..HEAD")).Out -split "`r?`n" |
                  Where-Object { $_.Trim() -ne '' })
    $notMine = @($subjects | Where-Object { $_ -notlike 'Auto-commit:*' })
    if ($notMine.Count -gt 0) {
        Fail "This folder has commits GitHub does not have, and they were not made by the watcher." `
             ("Nothing has been changed. These are the commits:`r`n  " + ($notMine -join "`r`n  "))
    }

    Say "  Undoing $($subjects.Count) watcher commit(s) so the work can be replayed on current files..."
    $r = Invoke-G @('reset','--mixed',$mb)
    if ($r.Code -ne 0) { Fail 'Could not undo the watcher commit.' $r.Out }
    Say "    back to $((Invoke-G @('rev-parse','--short','HEAD')).Out), with every change still on disk"
}

# --- 2. Drop the two edits made against the old files -------------------------
# These are the only files we touched that GitHub also changed. The corrected
# copies in tools\pending go back in after the sync. Everything else we changed
# is untouched upstream, so it can ride through the fast-forward as-is and no
# stash is needed.

Say '  Dropping the two edits made against the old versions...'
Invoke-G @('checkout','--','.gitignore','home/models.py') | Out-Null

# --- 3. Catch up --------------------------------------------------------------

Say '  Catching up to GitHub...'
$r = Invoke-G @('merge','--ff-only',"origin/$Branch")
if ($r.Code -ne 0) {
    Fail 'Could not catch up to GitHub without overwriting local work.' `
         ($r.Out + "`r`n`r`nNothing was moved. The file named above was changed both here and on GitHub.")
}
Say "    now at $((Invoke-G @('rev-parse','--short','HEAD')).Out)"

# --- 4. Put the corrected versions in place -----------------------------------

Say '  Applying the corrected .gitignore and home/models.py...'
Copy-Item (Join-Path $Pending 'gitignore.txt')   (Join-Path $Repo '.gitignore')      -Force
Copy-Item (Join-Path $Pending 'home_models.py')  (Join-Path $Repo 'home\models.py')  -Force

# --- 5. Commit and push -------------------------------------------------------

# Stale by now, and it must not end up in the commit.
Remove-Item (Join-Path $Repo 'AUTOPUSH-BLOCKED.txt') -Force -ErrorAction SilentlyContinue

$r = Invoke-G @('add','-A')
if ($r.Code -ne 0) { Fail 'git add failed.' $r.Out }

$staged = @((Invoke-G @('diff','--cached','--name-only')).Out -split "`r?`n" | Where-Object { $_.Trim() -ne '' })
if ($staged.Count -eq 0) {
    Say ''
    Say '  Nothing left to commit - this folder already matches GitHub.'
    Say ''
    exit 0
}

Say ''
Say "  Committing $($staged.Count) file(s):"
$staged | ForEach-Object { Say "    $_" }
Say ''

$msgFile = Join-Path $env:TEMP "sync-and-push-msg.txt"
$lines = @(
    'Store: editable products and categories in the admin',
    '',
    'Products and their category buckets are now managed from a Store section',
    'in the Wagtail sidebar instead of a hardcoded list. Categories become a',
    'ProductCategory model, StoreProduct.category becomes a foreign key to it,',
    'and both store page types render the same listing partial.',
    '',
    'Adds manage.py store_pages to report which store page is live.',
    '',
    'Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>'
)
Set-Content -Path $msgFile -Value ($lines -join [Environment]::NewLine) -Encoding UTF8
$r = Invoke-G @('commit','-F',$msgFile)
Remove-Item $msgFile -Force -ErrorAction SilentlyContinue
if ($r.Code -ne 0) { Fail 'git commit failed.' $r.Out }

Say '  Pushing to GitHub...'
Say '  (If a sign-in window opens, approve it.)'
$r = Invoke-G @('push','origin',$Branch)
if ($r.Code -ne 0) {
    Fail 'The push was rejected.' ($r.Out + "`r`n`r`nThe commit is saved locally, so nothing is lost.")
}

Remove-Item (Join-Path $Repo 'AUTOPUSH-BLOCKED.txt') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Repo '.autopush-pause')      -Force -ErrorAction SilentlyContinue

Say ''
Say '=================================================================='
Say "  Pushed. GitHub is now at $((Invoke-G @('rev-parse','--short','HEAD')).Out)."
Say '  The watcher is un-paused and back on its 5-minute schedule.'
Say ''
Say '  DigitalOcean should start building within a minute. Watch it at'
Say '  https://cloud.digitalocean.com/apps - and check that the migrate'
Say '  job runs before the web service starts.'
Say ''
Say '  The watcher takes over from here. You should not need to run'
Say '  this file again.'
Say '=================================================================='
Say ''

<#
Expire noncurrent object versions after 30 days on both Spaces buckets, so
deleted or replaced files don't outlive the Privacy Policy's 30-day promise.

    powershell -ExecutionPolicy Bypass -File tools\spaces_lifecycle.ps1

Run it yourself in a separate PowerShell window. It asks for a Full Access
Spaces key and secret (typed input is hidden), applies one lifecycle rule to
each bucket with the amazon/aws-cli Docker image, then reads each rule back
and prints only the bucket, rule ID and NoncurrentDays.

The key and secret never appear on a command line, in history, in a file or
in a log: they are held as SecureStrings, copied into this process's
environment only for the docker calls (passed by name with -e), and wiped at
the end. The lifecycle JSON holds no secrets; it goes in a temp folder that
is deleted afterwards. Delete the access key in the control panel when done.
#>
$ErrorActionPreference = "Stop"

$Buckets = @("sitesofgrace-media2", "sitesofgrace-pilgrims")
$Endpoint = "https://sfo3.digitaloceanspaces.com"
$Region = "sfo3"
$Image = "amazon/aws-cli:2.17.0"

# This machine's TLS inspection (Norton) re-signs HTTPS; trust its root
# inside the container if the dev cert is present, as the dev image does.
$RepoRoot = Split-Path -Parent $PSScriptRoot
$NortonCert = Join-Path $RepoRoot "docker\dev-certs\norton-root.crt"

$Rule = @'
{
  "Rules": [
    {
      "ID": "expire-noncurrent-30d",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "NoncurrentVersionExpiration": {"NoncurrentDays": 30},
      "Expiration": {"ExpiredObjectDeleteMarker": true}
    }
  ]
}
'@

function Get-Plain([Security.SecureString]$Secure) {
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

$TempDir = Join-Path ([IO.Path]::GetTempPath()) ("sog-lifecycle-" + [Guid]::NewGuid().ToString("N"))
$KeySecure = $null
$SecretSecure = $null
try {
    $KeySecure = Read-Host "Spaces access key (Full Access)" -AsSecureString
    $SecretSecure = Read-Host "Spaces secret" -AsSecureString

    New-Item -ItemType Directory -Path $TempDir | Out-Null
    $RuleFile = Join-Path $TempDir "lifecycle.json"
    [IO.File]::WriteAllText($RuleFile, $Rule, (New-Object Text.UTF8Encoding($false)))

    $DockerArgs = @("run", "--rm", "-e", "AWS_ACCESS_KEY_ID", "-e", "AWS_SECRET_ACCESS_KEY",
                    "-e", "AWS_DEFAULT_REGION=$Region", "-v", "${TempDir}:/cfg:ro")
    if (Test-Path $NortonCert) {
        $DockerArgs += @("-v", "${NortonCert}:/certs/root.crt:ro", "-e", "AWS_CA_BUNDLE=/certs/root.crt")
    }
    $DockerArgs += $Image

    # Process-scope only, for the docker calls below; removed in finally.
    $env:AWS_ACCESS_KEY_ID = Get-Plain $KeySecure
    $env:AWS_SECRET_ACCESS_KEY = Get-Plain $SecretSecure

    foreach ($Bucket in $Buckets) {
        & docker @DockerArgs s3api put-bucket-lifecycle-configuration --endpoint-url $Endpoint `
            --bucket $Bucket --lifecycle-configuration file:///cfg/lifecycle.json
        if ($LASTEXITCODE -ne 0) { throw "put-bucket-lifecycle-configuration failed for $Bucket" }
    }
    foreach ($Bucket in $Buckets) {
        $Lines = & docker @DockerArgs s3api get-bucket-lifecycle-configuration --endpoint-url $Endpoint `
            --bucket $Bucket --query "Rules[].[ID,NoncurrentVersionExpiration.NoncurrentDays]" --output text
        if ($LASTEXITCODE -ne 0) { throw "get-bucket-lifecycle-configuration failed for $Bucket" }
        foreach ($Line in @($Lines)) {
            $Parts = "$Line" -split "\s+"
            Write-Host ("{0}  rule={1}  NoncurrentDays={2}" -f $Bucket, $Parts[0], $Parts[1])
        }
    }
}
finally {
    Remove-Item Env:AWS_ACCESS_KEY_ID -ErrorAction SilentlyContinue
    Remove-Item Env:AWS_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue
    if ($KeySecure) { $KeySecure.Dispose() }
    if ($SecretSecure) { $SecretSecure.Dispose() }
    Remove-Variable KeySecure, SecretSecure -ErrorAction SilentlyContinue
    if (Test-Path $TempDir) { Remove-Item -Recurse -Force $TempDir }
    Write-Host "Done. Temp files removed and credentials cleared. Now delete the access key in the control panel."
}

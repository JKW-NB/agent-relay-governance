param(
    [ValidateRange(1024,65535)][int]$SourcePort = 1934,
    [ValidateRange(1024,65535)][int]$RestorePort = 1935,
    [string]$Python = 'D:\DevTools\PythonEnvs\main\python.exe',
    [string]$Docker = 'D:\DevTools\Docker\Desktop\resources\bin\docker.exe'
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$runtime = Join-Path $project 'openviking-runtime'
$source = Join-Path $runtime "compose-$SourcePort"
$restore = Join-Path $runtime "compose-$RestorePort"
if ($SourcePort -eq 1933 -or $RestorePort -eq 1933 -or $SourcePort -eq $RestorePort -or
    (Test-Path -LiteralPath $restore)) { throw 'Use an isolated source and an unused restore directory' }
if (Get-NetTCPConnection -LocalPort $RestorePort -State Listen -ErrorAction SilentlyContinue) {
    throw 'Restore port is already in use'
}
$stamp = Get-Date -Format yyyyMMdd-HHmmss
$backup = Join-Path $runtime "backup-$SourcePort-$stamp"
$items = @('ov/ov.conf','ov/data','ov/approval-active-index.json')
foreach ($item in $items) {
    if (!(Test-Path -LiteralPath (Join-Path $source $item))) { throw "Missing backup input: $item" }
}
function Set-Stack([int]$port, [string]$stackDirectory) {
    $env:ARG_POC_STACK_PORT = "$port"
    $env:ARG_POC_STACK_HOME = $stackDirectory
    $env:ARG_POC_RUNTIME = Join-Path $stackDirectory 'ov'
    $env:ARG_POC_OV_URL = "http://127.0.0.1:$port"
}
function Invoke-Compose {
    & $Docker compose -p "arg-ov-poc-$env:ARG_POC_STACK_PORT" -f (Join-Path $PSScriptRoot 'compose.yaml') @args
    if ($LASTEXITCODE) { throw 'Compose operation failed' }
}
function Wait-Healthy([int]$port) {
    for ($i=0; $i -lt 35; $i++) {
        try {
            $health = Invoke-RestMethod "http://127.0.0.1:$port/health" -TimeoutSec 2
            if ($health.healthy) { return $health.version }
        } catch {}
        Start-Sleep -Seconds 1
    }
    throw "Instance $port failed readiness"
}
function Copy-StackFiles([string]$from, [string]$to) {
    New-Item -ItemType Directory -Path $to | Out-Null
    foreach ($item in $items) {
        $dest = Join-Path $to $item
        New-Item -ItemType Directory -Path (Split-Path $dest) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $from $item) -Destination $dest -Recurse
    }
}
function Get-Manifest([string]$root) {
    $rows = foreach ($item in $items) {
        Get-ChildItem -LiteralPath (Join-Path $root $item) -File -Recurse -Force | ForEach-Object {
            [pscustomobject]@{
                path = [IO.Path]::GetRelativePath($root,$_.FullName)
                sha256 = (Get-FileHash -LiteralPath $_.FullName).Hash
            }
        }
    }
    $rows | Sort-Object path
}
function Get-EmbeddingDigest([int]$port) {
    $probe = 'import json,urllib.request; d=json.load(urllib.request.urlopen("http://ollama:11434/api/tags",timeout=5)); print(next(m["digest"] for m in d["models"] if m["name"]=="nomic-embed-text:v1.5"))'
    $digest = & $Docker exec "arg-ov-poc-$port-openviking-1" python -c $probe
    if ($LASTEXITCODE -or $digest -notmatch '^[a-f0-9]{64}$') { throw "Model digest unavailable on port $port" }
    $digest
}
function Read-Approval {
    $out = & $Python -B (Join-Path $PSScriptRoot 'query_approval.py') 'Is the approval to verify the relay archive with SHA-256 still valid?' --as-of 2026-10-12
    if ($LASTEXITCODE) { throw 'Approval query failed' }
    $out -join "`n" | ConvertFrom-Json
}

Set-Stack $SourcePort $source
$version = Wait-Healthy $SourcePort
$sourceDigest = Get-EmbeddingDigest $SourcePort
$before = Read-Approval
if ($before.status -ne 'revoked') { throw 'Unexpected source baseline' }
try {
    Invoke-Compose stop openviking
    Copy-StackFiles $source $backup
    $manifest = @(Get-Manifest $source)
    if (Compare-Object $manifest @(Get-Manifest $backup) -Property path,sha256) { throw 'Backup hashes differ' }
} finally {
    Invoke-Compose up -d openviking
}
$null = Wait-Healthy $SourcePort
Copy-StackFiles $backup $restore
if (Compare-Object $manifest @(Get-Manifest $restore) -Property path,sha256) { throw 'Restore hashes differ' }
& (Join-Path $PSScriptRoot 'start_clean_stack.ps1') -Port $RestorePort -Docker $Docker -Python $Python
Set-Stack $RestorePort $restore
$restoredDigest = Get-EmbeddingDigest $RestorePort
if ($restoredDigest -cne $sourceDigest) { throw 'Restored embedding model digest differs' }
$after = Read-Approval
if ($after.status -ne $before.status -or $after.hit_source_uri -ne $before.hit_source_uri -or
    $after.state_source.id -ne $before.state_source.id) { throw 'Restored query differs' }
$report = Join-Path $runtime "backup-restore-$stamp.json"
@{
    source_port=$SourcePort; restored_port=$RestorePort; version=$version; model_reacquired=$true
    snapshot=$backup; restored_directory=$restore; file_count=$manifest.Count; files=$manifest
    source_result=$before; restored_result=$after
    original_health=(Wait-Healthy $SourcePort); main_health=(Wait-Healthy 1933)
    source_model_digest=$sourceDigest; restored_model_digest=$restoredDigest
} | ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $report -Encoding utf8
$report

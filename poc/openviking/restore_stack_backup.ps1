param(
    [Parameter(Mandatory)][string]$Report,
    [string]$IntegrityReport,
    [ValidateRange(1024,65535)][int]$Port = 1936,
    [string]$Python = 'D:\DevTools\PythonEnvs\main\python.exe',
    [string]$Docker = 'D:\DevTools\Docker\Desktop\resources\bin\docker.exe'
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$runtime = Join-Path $project 'openviking-runtime'
$reportPath = (Resolve-Path -LiteralPath $Report).Path
$backupMetadata = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
$snapshot = (Resolve-Path -LiteralPath $backupMetadata.snapshot).Path
$target = Join-Path $runtime "compose-$Port"
if (!$snapshot.StartsWith("$runtime\backup-", [StringComparison]::OrdinalIgnoreCase) -or
    $Port -eq 1933 -or (Test-Path -LiteralPath $target)) {
    throw 'Use a project snapshot and an unused isolated restore directory'
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw 'Restore port is already in use'
}

$expectedDigest = $backupMetadata.source_model_digest
if (!$expectedDigest -and $IntegrityReport) {
    $integrity = Get-Content -LiteralPath $IntegrityReport -Raw | ConvertFrom-Json
    if ($integrity.backup_report -ne $reportPath) { throw 'Model evidence is for a different backup report' }
    $expectedDigest = $integrity.source_model_digest
}
if ($expectedDigest -notmatch '^[a-f0-9]{64}$') { throw 'Source model digest is required' }

$verifier = Join-Path $PSScriptRoot 'verify_stack_backup.py'
& $Python -B $verifier $reportPath
if ($LASTEXITCODE) { throw 'Snapshot integrity check failed before restore' }

New-Item -ItemType Directory -Path (Join-Path $target 'ov') | Out-Null
foreach ($item in 'ov.conf','data','approval-active-index.json') {
    Copy-Item -LiteralPath (Join-Path $snapshot "ov/$item") -Destination (Join-Path $target "ov/$item") -Recurse
}
$copyManifest = Join-Path $target 'restored-file-check.json'
@{snapshot=$target; files=$backupMetadata.files} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $copyManifest -Encoding utf8
& $Python -B $verifier $copyManifest
if ($LASTEXITCODE) { throw 'Restored copy failed integrity check' }

$start = Join-Path $PSScriptRoot 'start_clean_stack.ps1'
$queryOutput = & $start -Port $Port -Python $Python -Docker $Docker
$answer = $queryOutput -join "`n" | ConvertFrom-Json
$probe = 'import json,urllib.request; d=json.load(urllib.request.urlopen("http://ollama:11434/api/tags",timeout=5)); print(next(m["digest"] for m in d["models"] if m["name"]=="nomic-embed-text:v1.5"))'
$actualDigest = & $Docker exec "arg-ov-poc-$Port-openviking-1" python -c $probe
if ($LASTEXITCODE -or $actualDigest -cne $expectedDigest -or
    $answer.status -ne $backupMetadata.source_result.status -or
    $answer.hit_source_uri -ne $backupMetadata.source_result.hit_source_uri -or
    $answer.state_source.id -ne $backupMetadata.source_result.state_source.id) {
    throw 'Restored model or query differs from the backup baseline'
}
$output = Join-Path $runtime "restore-from-report-$Port-$(Get-Date -Format yyyyMMdd-HHmmss).json"
@{source_report=$reportPath; target_port=$Port; files=$backupMetadata.files.Count
  model_digest=$actualDigest; result=$answer; restored_directory=$target} |
    ConvertTo-Json -Depth 16 | Set-Content -LiteralPath $output -Encoding utf8
$output

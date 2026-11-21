param(
    [ValidateRange(1024,65535)][int]$Port = 1934,
    [string]$Python = 'D:\DevTools\PythonEnvs\main\python.exe',
    [string]$Docker = 'D:\DevTools\Docker\Desktop\resources\bin\docker.exe'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$stackHome = Join-Path $projectRoot "openviking-runtime\compose-$Port"
$ovHome = Join-Path $stackHome 'ov'
$env:ARG_POC_STACK_HOME = $stackHome
$env:ARG_POC_STACK_PORT = "$Port"
$env:ARG_POC_OV_URL = "http://127.0.0.1:$Port"
$env:ARG_POC_RUNTIME = $ovHome
$env:Path = "$(Split-Path $Docker);$env:Path"
$compose = @('compose', '-p', "arg-ov-poc-$Port", '-f', (Join-Path $PSScriptRoot 'compose.yaml'))

function Invoke-Compose {
    & $Docker @compose @args
    if ($LASTEXITCODE) { throw "Compose failed with exit code $LASTEXITCODE" }
}

New-Item -ItemType Directory -Path $ovHome,(Join-Path $stackHome 'ollama') -Force | Out-Null
$config = Join-Path $ovHome 'ov.conf'
if (!(Test-Path -LiteralPath $config)) {
    $key = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    @{
        server = @{host='0.0.0.0'; port=1933; auth_mode='trusted'; root_api_key=$key}
        storage = @{workspace='/app/.openviking/data'}
        embedding = @{dense=@{
            provider='ollama'; model='nomic-embed-text:v1.5'; dimension=768
            api_base='http://ollama:11434/v1'; api_key='ollama'
        }}
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $config -Encoding utf8
}

Invoke-Compose up -d ollama
for ($i=0; $i -lt 20; $i++) {
    & $Docker @compose exec -T ollama ollama list 2>$null | Out-Null
    if (!$LASTEXITCODE) { break }
    Start-Sleep -Seconds 1
}
if ($LASTEXITCODE) { throw 'Ollama did not become ready' }
& $Docker @compose exec -T ollama ollama show nomic-embed-text:v1.5 2>$null | Out-Null
if ($LASTEXITCODE) { Invoke-Compose exec -T ollama ollama pull nomic-embed-text:v1.5 }
Invoke-Compose up -d openviking
for ($i=0; $i -lt 35; $i++) {
    try {
        $health = Invoke-RestMethod "$env:ARG_POC_OV_URL/health" -TimeoutSec 2
        if ($health.healthy) { break }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (!$health.healthy) { throw 'OpenViking did not become ready' }
$pointer = Join-Path $ovHome 'approval-active-index.json'
if (Test-Path -LiteralPath $pointer) {
    $result = & $Python -B (Join-Path $PSScriptRoot 'query_approval.py') 'Is the approval to verify the relay archive with SHA-256 still valid?' --as-of 2026-10-12
    if ($LASTEXITCODE -or ($result -join "`n" | ConvertFrom-Json).status -ne 'revoked') {
        throw 'Existing POC index did not pass its startup query'
    }
    $result
    return
}
& $Python -B (Join-Path $PSScriptRoot 'bootstrap_approval_index.py') --activate-if-empty
if ($LASTEXITCODE) { throw 'Index bootstrap failed' }

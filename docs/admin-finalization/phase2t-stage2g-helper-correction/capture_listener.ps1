param([Parameter(Mandatory=$true)][string]$RunDirectory)
$ErrorActionPreference = 'Stop'
$proofPath = $null
try {
    $proofDirectory = (Resolve-Path -LiteralPath $RunDirectory).Path
    $proofWorkspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
    if (-not $proofDirectory.StartsWith($proofWorkspace + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Workspace required'
    }
    $proofPath = Join-Path $proofDirectory 'listener-proof.json'
    $ready = Get-Content -LiteralPath (Join-Path $proofDirectory 'ready.json') -Raw | ConvertFrom-Json
    if ($ready.origin -ne 'http://127.0.0.1:5000' -or $ready.run_id -notmatch '^[a-f0-9]{32}$' -or $ready.armed -ne $false) {
        throw 'Invalid ready metadata'
    }
    $rows = @(Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort 5000 -ErrorAction Stop |
        Select-Object LocalAddress,LocalPort,OwningProcess)
    $owners = @($rows | Where-Object { $_.OwningProcess -gt 0 } | Select-Object -ExpandProperty OwningProcess -Unique)
    $ok = $owners.Count -eq 1 -and $owners[0] -eq $ready.pid
    $proof = [ordered]@{ok=[bool]$ok;source='Get-NetTCPConnection';observed_utc=[DateTime]::UtcNow.ToString('o');
        run_id=$ready.run_id;origin='http://127.0.0.1:5000';listeners=$rows}
    $proof | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $proofPath -Encoding UTF8
    @{passed=[bool]$ok;stage='native_listener_capture'} | ConvertTo-Json |
        Set-Content -LiteralPath (Join-Path $proofDirectory 'listener-query-result.json') -Encoding UTF8
    @{passed=[bool]$ok;stage='native_listener_capture'} | ConvertTo-Json -Compress
    if (-not $ok) { exit 1 }
} catch {
    $safeExceptionClass = $_.Exception.GetType().Name
    # Replace any old proof with a failed envelope; do not preserve stale success.
    if ($null -ne $proofPath) {
        try { @{ok=$false;source='Get-NetTCPConnection'} | ConvertTo-Json | Set-Content -LiteralPath $proofPath -Encoding UTF8 } catch {}
        try {
            @{passed=$false;stage='native_listener_capture';exception_class=$safeExceptionClass} | ConvertTo-Json |
                Set-Content -LiteralPath (Join-Path $proofDirectory 'listener-query-result.json') -Encoding UTF8
        } catch {}
    }
    @{passed=$false;stage='native_listener_capture';exception_class=$safeExceptionClass} |
        ConvertTo-Json -Compress
    exit 1
}

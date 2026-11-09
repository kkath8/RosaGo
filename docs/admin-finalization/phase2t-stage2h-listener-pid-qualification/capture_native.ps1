param([Parameter(Mandatory=$true)][string]$RunDirectory)
$ErrorActionPreference='Stop'
$path=$null
try {
    $directory=(Resolve-Path -LiteralPath $RunDirectory).Path
    $workspace=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
    if (-not $directory.StartsWith($workspace+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {throw 'Workspace required'}
    $path=Join-Path $directory 'native-input.json'
    @{pending=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'listener-qualification.pending') -Encoding UTF8
    $ready=Get-Content -LiteralPath (Join-Path $directory 'ready.json') -Raw | ConvertFrom-Json
    if ($ready.origin -ne 'http://127.0.0.1:5000' -or $ready.run_id -notmatch '^[a-f0-9]{32}$' -or $ready.armed -ne $false) {throw 'Invalid ready metadata'}
    $psRows=@();$psExit=0;$psError=$null
    try {
        $psRows=@(Get-NetTCPConnection -LocalPort 5000 -ErrorAction Stop |
            ForEach-Object { @{LocalAddress=$_.LocalAddress;LocalPort=[int]$_.LocalPort;OwningProcess=[int]$_.OwningProcess;State=[string]$_.State} })
    } catch {$psExit=1;$psError=$_.Exception.GetType().Name}
    $text=@(& "$env:SystemRoot\System32\netstat.exe" -ano)
    $nsExit=$LASTEXITCODE
    # Persist only rows for the exact target port, never full connection inventory.
    $selected=@($text | Where-Object {
        $fields=@($_.Trim() -split '\s+')
        $fields.Count -eq 5 -and $fields[0] -eq 'TCP' -and $fields[1] -match ':5000$'
    }) -join "`n"
    $inputObject=@{run_id=$ready.run_id;origin=$ready.origin;observed_utc=[DateTime]::UtcNow.ToString('o');
        powershell_rows=$psRows;powershell_exit=$psExit;powershell_error_class=$psError;
        netstat_text=$selected;netstat_exit=$nsExit}
    # This input is transient: normalizer removes raw rows after reading it.
    $inputObject | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $path -Encoding UTF8
    @{stage='native_sources_collected';powershell_exit=$psExit;netstat_exit=$nsExit} | ConvertTo-Json -Compress
} catch {
    if ($null -ne $path) {@{capture_failed=$true} | ConvertTo-Json | Set-Content -LiteralPath $path -Encoding UTF8}
    @{stage='native_sources_failed';exception_class=$_.Exception.GetType().Name} | ConvertTo-Json -Compress
    exit 1
}

param([ValidateSet('sandbox','host')][string]$Context='sandbox')
$ErrorActionPreference='Stop'
$token=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=[Security.Principal.WindowsPrincipal]::new($token)
$result=[ordered]@{
    phase='2T Stage 2I';context=$Context;pid=$PID;
    managed_pid=[Diagnostics.Process]::GetCurrentProcess().Id;
    administrator_token=$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator);
    system_token=$token.IsSystem;is_64_bit=[Environment]::Is64BitProcess;
    powershell_major=$PSVersionTable.PSVersion.Major;
    execution_policy=[string](Get-ExecutionPolicy);
    werkzeug_run_main_present=Test-Path Env:WERKZEUG_RUN_MAIN;
    observations=@();authentication_requests=0;application_payload_bytes=0
}
$token.Dispose()
try {
    $result.parent_pid=[int](Get-CimInstance Win32_Process -Filter "ProcessId=$PID" -ErrorAction Stop).ParentProcessId
} catch { $result.parent_query_error=$_.Exception.GetType().Name }
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,0)
$client=$null;$accepted=$null
try {
    $listener.Start();$port=$listener.LocalEndpoint.Port;$result.port=$port
    foreach ($phaseName in @('bound_immediate','bound_after_delay','after_empty_accept')) {
        if ($phaseName -eq 'bound_after_delay') {Start-Sleep -Seconds 2}
        if ($phaseName -eq 'after_empty_accept') {
            $client=[Net.Sockets.TcpClient]::new();$client.Connect([Net.IPAddress]::Loopback,$port)
            $accepted=$listener.AcceptTcpClient();Start-Sleep -Seconds 1
        }
        $item=[ordered]@{phase=$phaseName;utc=[DateTime]::UtcNow.ToString('o');
            socket_bound=$listener.Server.IsBound;
            socket_accept_flag=$listener.Server.GetSocketOption([Net.Sockets.SocketOptionLevel]::Socket,[Net.Sockets.SocketOptionName]::AcceptConnection);
            target_native_rows=@();native_error=$null;target_netstat_rows=@()}
        try {
            $allNative=@(Get-NetTCPConnection -ErrorAction Stop)
            $item.native_query_succeeded=$true
            $item.native_global_listen_count=@($allNative | Where-Object {$_.State -eq 'Listen'}).Count
            $item.target_native_rows=@($allNative | Where-Object {$_.LocalPort -eq $port -and $_.LocalAddress -eq '127.0.0.1'} |
                ForEach-Object { @{state=[string]$_.State;state_numeric=[int]$_.State;pid=[int]$_.OwningProcess} })
        } catch {
            $item.native_query_succeeded=$false
            $item.native_error=$_.Exception.GetType().Name
            $item.native_error_category=[string]$_.CategoryInfo.Category
        }
        $table=@(& "$env:SystemRoot\System32\netstat.exe" -ano)
        $item.netstat_exit=$LASTEXITCODE
        $item.netstat_global_listen_count=0
        $item.netstat_tcp_rows=0
        foreach ($line in $table) {
            $parts=@($line.Trim() -split '\s+')
            if ($parts.Count -ne 5 -or $parts[0] -ne 'TCP') {continue}
            $item.netstat_tcp_rows++
            if ($parts[3] -eq 'LISTENING') {$item.netstat_global_listen_count++}
            if ($parts[1] -eq "127.0.0.1:$port") {
                $owner=0
                if ([int]::TryParse($parts[4],[ref]$owner)) {
                    $safeState=if ($parts[3] -in @('LISTENING','ESTABLISHED','TIME_WAIT','FIN_WAIT_1','FIN_WAIT_2','CLOSE_WAIT')) {$parts[3]} else {'OTHER'}
                    $item.target_netstat_rows+=@{state=$safeState;pid=$owner}
                }
            }
        }
        $item.netstat_embedded_nul=@($table | Where-Object {$_.Contains([string][char]0)}).Count -gt 0
        $result.observations+=,$item
    }
} catch { $result.fixture_error_class=$_.Exception.GetType().Name }
finally {
    if ($null -ne $accepted) {$accepted.Dispose()}
    if ($null -ne $client) {$client.Dispose()}
    $listener.Stop();$result.fixture_closed=$true
}
$result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ("context-$Context.json")) -Encoding UTF8
$result | ConvertTo-Json -Depth 7

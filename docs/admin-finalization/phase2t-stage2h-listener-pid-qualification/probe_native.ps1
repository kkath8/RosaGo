param([string]$OutputName='native-probe.json',[ValidateRange(0,65535)][int]$Port=0)
$ErrorActionPreference='Stop'
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$Port)
$client=$null
$accepted=$null
$result=[ordered]@{fixture='owned_dotnet_loopback';expected_pid=$PID;authentication_requests=0;observations=@()}
try {
    $listener.Start()
    $port=$listener.LocalEndpoint.Port
    $result.port=$port
    $result.listener_is_bound=$listener.Server.IsBound
    # Establish a controlled empty TCP connection; no HTTP/application payload.
    $client=[Net.Sockets.TcpClient]::new()
    $client.Connect([Net.IPAddress]::Loopback,$port)
    $accepted=$listener.AcceptTcpClient()
    $result.empty_tcp_connection_established=$client.Connected -and $accepted.Connected
    foreach ($attempt in 1..3) {
        $row=[ordered]@{attempt=$attempt;native_rows=@();native_error=$null;netstat_exit=$null;netstat_rows=@()}
        try {
            $row.native_rows=@(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop |
                Select-Object LocalAddress,LocalPort,OwningProcess)
        } catch { $row.native_error=$_.Exception.GetType().Name }
        try {
            $row.native_all_target_states=@(Get-NetTCPConnection -LocalPort $port -ErrorAction Stop |
                ForEach-Object { @{LocalAddress=$_.LocalAddress;LocalPort=[int]$_.LocalPort;
                    OwningProcess=[int]$_.OwningProcess;State=[string]$_.State} })
        } catch { $row.native_all_states_error=$_.Exception.GetType().Name }
        $row.socket_accepts_connections=$listener.Server.GetSocketOption([Net.Sockets.SocketOptionLevel]::Socket,[Net.Sockets.SocketOptionName]::AcceptConnection)
        $row.socket_is_bound=$listener.Server.IsBound
        $row.dotnet_listener_matches=@([Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() | Where-Object { $_.Port -eq $port }).Count
        $text=@(& "$env:SystemRoot\System32\netstat.exe" -ano)
        $row.netstat_exit=$LASTEXITCODE
        $row.netstat_line_count=$text.Count
        $row.netstat_tcp_line_count=@($text | Where-Object { $_ -match '^\s*TCP\s+' }).Count
        $row.netstat_embedded_nul=@($text | Where-Object { $_.Contains([string][char]0) }).Count -gt 0
        $row.own_tcp_rows=@()
        foreach ($line in $text) {
            $fields=@($line.Trim() -split '\s+')
            if ($fields.Count -eq 5 -and $fields[0] -eq 'TCP' -and $fields[4] -eq [string]$PID) {
                $local=$fields[1]
                if ($local -match '^(127\.0\.0\.1|0\.0\.0\.0|\[::1\]|\[::\]):\d+$') {
                    $row.own_tcp_rows+=@{local_endpoint=$local;state=$fields[3];pid=$PID}
                }
            }
            if ($fields.Count -eq 5 -and $fields[0] -eq 'TCP' -and $fields[1] -eq "127.0.0.1:$port") {
                $owner=0
                if ([int]::TryParse($fields[4],[ref]$owner)) {
                    $row.netstat_rows+=@{LocalAddress='127.0.0.1';LocalPort=$port;OwningProcess=$owner;State=$fields[3]}
                }
            }
        }
        $result.observations+=,$row
        if ($attempt -lt 3) { Start-Sleep -Seconds 2 }
    }
    $result.get_net_tcp_parameters=@((Get-Command Get-NetTCPConnection).Parameters.Keys)
    $result.process_64_bit=[Environment]::Is64BitProcess
} catch {
    $result.exception_class=$_.Exception.GetType().Name
} finally {
    if ($null -ne $accepted) {$accepted.Dispose()}
    if ($null -ne $client) {$client.Dispose()}
    $listener.Stop()
    $result.fixture_closed=$true
}
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot $OutputName) -Encoding UTF8
$result | ConvertTo-Json -Depth 8

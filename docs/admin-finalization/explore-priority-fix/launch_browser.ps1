# Task-owned headless Chrome; no existing profile or real account data.
$ErrorActionPreference = 'Stop'
$priorityProfile = Join-Path $env:TEMP ('rosago-priority-browser-' + [guid]::NewGuid().ToString('N'))
$priorityArgs = @('--headless=new', '--remote-debugging-port=9266', '--remote-debugging-address=127.0.0.1', ('--user-data-dir="' + $priorityProfile + '"'), '--no-first-run', '--no-default-browser-check', '--disable-sync', '--disable-extensions', '--disable-background-networking', '--disable-component-update', '--disable-default-apps', '--host-resolver-rules="MAP * ~NOTFOUND, EXCLUDE 127.0.0.1"', 'about:blank')
$priorityBrowser = Start-Process -FilePath 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList $priorityArgs -WindowStyle Hidden -PassThru
@{pid=$priorityBrowser.Id;profile=$priorityProfile;debugging_port=9266;headless=$true;parent_waits_for_browser=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'browser-process.json') -Encoding UTF8
Wait-Process -Id $priorityBrowser.Id

# Local integrity/clipboard helper only. Never connects to or executes SQL.
[CmdletBinding()]
param(
    [ValidateSet('private_sessions.review.sql','provider_access_guards.review.sql')]
    [string]$Copy
)

$ErrorActionPreference = 'Stop'
$expectedProject = 'jfaufpfzfhysqkhcdsrs'
$expected = [ordered]@{
    'private_sessions.review.sql' = '59899c43c3d3bfe232b9b91e87b979a3fa3338e2dd8ed7d070768fc6b05555ea'
    'provider_access_guards.review.sql' = '4136cd079ad39201e3fb185c0de8410374a556cb38631f25ac51e81c19983307'
}
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json
if ($manifest.target_project_ref -ne $expectedProject -or @($manifest.ordered_sql).Count -ne 2) {
    throw 'STOP: Review manifest target or inventory differs.'
}
$buffers = @{}
$sha = [System.Security.Cryptography.SHA256]::Create()
try {
    foreach ($name in $expected.Keys) {
        $entry = @($manifest.ordered_sql | Where-Object { $_.file -eq "evaluation/infrastructure/sql/$name" })
        if ($entry.Count -ne 1 -or $entry[0].sha256 -cne $expected[$name]) {
            throw "STOP: Recorded approval hash differs for $name"
        }
        $buffers[$name] = [System.IO.File]::ReadAllBytes((Join-Path $PSScriptRoot "sql/$name"))
        $actual = ([System.BitConverter]::ToString($sha.ComputeHash($buffers[$name]))).Replace('-', '').ToLowerInvariant()
        if ($actual -cne $expected[$name]) { throw "STOP: File hash differs for $name" }
        Write-Output "PASS: $name SHA256 $actual"
    }
} finally {
    $sha.Dispose()
}
Write-Output "PASS: Review manifest names evaluation project $expectedProject. No hosted changes made."
Write-Output 'Dashboard target must still be checked separately; this helper has no project connection.'
if ($Copy) {
    # Copy the SAME verified bytes; no second file read after hash verification.
    $text = [System.Text.UTF8Encoding]::new($false, $true).GetString($buffers[$Copy])
    Set-Clipboard -Value $text
    Write-Output "Copied only $Copy. No SQL executed."
}

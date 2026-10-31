# Run validation runs (PROTOCOL.md): setups x examples x seeds.
# Usage examples:
#   validation\locate\run_all.ps1                                   # run 1: A, B, C on E1, E2, seeds 0-4
#   validation\locate\run_all.ps1 -Setups A,B -Gels -Folder runs-gels   # Amendment 1, V1'
#   validation\locate\run_all.ps1 -Setups A -Folder runs-A-repeat2      # the original's own spread
# Outputs: <Reference>\<Folder>\<setup>\<example>\seed<n>\ (pred_*.csv, Z_*.csv, run.json, log.txt)
param(
    [string]$Reference = "C:\Users\noapa\code\locate-reference",
    [string[]]$Setups = @("A", "B", "C"),
    [int[]]$Seeds = @(0, 1, 2, 3, 4),
    [switch]$Gels,
    [string]$Folder = "runs"
)

$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$runner = "$PSScriptRoot\run_locate.py"
$all = @{
    A = @{ Python = "$Reference\env-original\Scripts\python.exe"; Impl = "original";   Path = "" }
    B = @{ Python = "$Reference\env-port\Scripts\python.exe";     Impl = "lightning2"; Path = "$repo\src" }
    C = @{ Python = "$repo\.venv\Scripts\python.exe";             Impl = "lightning2"; Path = "" }
}
# A typed array: `if` would unwrap a one-item array to a plain string, which then passes nothing.
[string[]]$extra = @()
if ($Gels) { $extra = @("--gels") }
foreach ($name in $Setups) {
    $setup = $all[$name]
    foreach ($example in "E1", "E2") {
        foreach ($seed in $Seeds) {
            $out = "$Reference\$Folder\$name\$example\seed$seed"
            Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
            New-Item -ItemType Directory -Force $out | Out-Null
            $env:PYTHONPATH = $setup.Path
            $start = Get-Date
            & $setup.Python $runner $setup.Impl "$PSScriptRoot\data\$example" $seed $out @extra *> "$out\log.txt"
            $code = $LASTEXITCODE
            $seconds = [int]((Get-Date) - $start).TotalSeconds
            $epochs = if (Test-Path "$out\run.json") { (Get-Content "$out\run.json" | ConvertFrom-Json).epochs } else { "-" }
            Write-Output ("{0} {1} seed{2}: exit {3}, {4} epochs, {5} s" -f $name, $example, $seed, $code, $epochs, $seconds)
        }
    }
}
$env:PYTHONPATH = ""

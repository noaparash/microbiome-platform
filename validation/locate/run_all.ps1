# Run every validation run (PROTOCOL.md): A, B and C, on E1 and E2, seeds 0-4.
# Usage: validation\locate\run_all.ps1 [-Reference C:\Users\noapa\code\locate-reference]
# Outputs: <Reference>\runs\<A|B|C>\<E1|E2>\seed<n>\ (pred_val.csv, pred_train.csv, Z_*.csv, run.json, log.txt)
param([string]$Reference = "C:\Users\noapa\code\locate-reference")

$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$runner = "$PSScriptRoot\run_locate.py"
$setups = @(
    @{ Name = "A"; Python = "$Reference\env-original\Scripts\python.exe"; Impl = "original";   Path = "" },
    @{ Name = "B"; Python = "$Reference\env-port\Scripts\python.exe";     Impl = "lightning2"; Path = "$repo\src" },
    @{ Name = "C"; Python = "$repo\.venv\Scripts\python.exe";             Impl = "lightning2"; Path = "" }
)
foreach ($setup in $setups) {
    foreach ($example in "E1", "E2") {
        foreach ($seed in 0..4) {
            $out = "$Reference\runs\$($setup.Name)\$example\seed$seed"
            Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
            New-Item -ItemType Directory -Force $out | Out-Null
            $env:PYTHONPATH = $setup.Path
            $start = Get-Date
            & $setup.Python $runner $setup.Impl "$PSScriptRoot\data\$example" $seed $out *> "$out\log.txt"
            $code = $LASTEXITCODE
            $seconds = [int]((Get-Date) - $start).TotalSeconds
            $epochs = if (Test-Path "$out\run.json") { (Get-Content "$out\run.json" | ConvertFrom-Json).epochs } else { "-" }
            Write-Output ("{0} {1} seed{2}: exit {3}, {4} epochs, {5} s" -f $setup.Name, $example, $seed, $code, $epochs, $seconds)
        }
    }
}
$env:PYTHONPATH = ""

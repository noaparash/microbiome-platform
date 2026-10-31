# Diagnostic: is the ORIGINAL LOCATE (environment A) repeatable against itself under given settings?
# Runs A twice per example (seed 0) and prints epochs and the largest difference. Looks at A only.
# Usage: validation\locate\repeat_check.ps1 -Label single-thread -Threads 1
param([string]$Label, [int]$Threads = 0, [string]$Reference = "C:\Users\noapa\code\locate-reference")

$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
if ($Threads -gt 0) { $env:OMP_NUM_THREADS = "$Threads"; $env:MKL_NUM_THREADS = "$Threads" }
else { Remove-Item Env:OMP_NUM_THREADS, Env:MKL_NUM_THREADS -ErrorAction SilentlyContinue }
foreach ($example in "E1", "E2") {
    $outs = foreach ($i in 1, 2) {
        $out = "$Reference\diag\$Label\$example\run$i"
        Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
        & "$Reference\env-original\Scripts\python.exe" "$PSScriptRoot\run_locate.py" original "$PSScriptRoot\data\$example" 0 $out *> $null
        $out
    }
    & "$repo\.venv\Scripts\python.exe" -c @"
import json, sys
import numpy as np, pandas as pd
a, b = sys.argv[1], sys.argv[2]
d = max(np.abs(pd.read_csv(f'{a}/{n}.csv', index_col=0).to_numpy() - pd.read_csv(f'{b}/{n}.csv', index_col=0).to_numpy()).max()
        for n in ('pred_val', 'pred_train', 'Z_val', 'Z_train'))
e = [json.load(open(f'{p}/run.json'))['epochs'] for p in (a, b)]
print(f'{sys.argv[3]}: epochs {e[0]} / {e[1]}, max difference {d:.3g}')
"@ $outs[0] $outs[1] "$Label $example"
}
Remove-Item Env:OMP_NUM_THREADS, Env:MKL_NUM_THREADS -ErrorAction SilentlyContinue

# Run times of the platform's tools

Measured 2026-11-03/04 on a laptop (12th Gen Intel Core i7-1255U, 10 cores / 12 threads, 15.7 GB RAM, no GPU, Windows 11, Python 3.13.3), with the platform's own code path (`mp.analyze`, the same
workflow the website's background worker runs). Each analysis ran in its own process,
capped at 60 minutes for this measurement only: an entry "> 60 min" was stopped there
(the platform itself never stops a run). These are laptop timings; the timings that
matter are the lab server's, to be measured after deployment.

**How to read it**

- **Preprocessing (MIPMLP) is a one-time cost per dataset.** Its result is cached: every
  later analysis of the same data (another tool, or the same one again) starts from the
  cached table instantly. That is why, below, only the first analysis of each dataset pays
  it. LOCATE uses its own variant of the table (each feature z-scored), so it pays one more
  preprocessing pass the first time.
- **Runs happen in the background.** After clicking Run, the user gets a results link and
  can close the page; the analysis continues on the server and the page (or an optional
  email) shows the results when they are ready. The user is never blocked, even for the
  longest runs here.
- **Peak memory** is the most memory the analysis used at once (the whole process: Python,
  the data and the tool). It is what the lab server needs per analysis running at the same
  time. For a run stopped at 60 minutes it is the peak until then ("at least").
- **Large datasets need the lab server.** On the big public datasets (tens of thousands of
  taxa), some tools did not finish within an hour on the laptop.
- The data overview figures (added after this measurement) take about 16 to 39 s more on the
  big datasets, and a few seconds on the small ones.

## example-40

40 samples, 263 taxa → 144 features.

| Tool | Preprocessing | Tool itself | Total | Peak memory |
|---|---|---|---|---|
| MIPMLP (just preprocess) | 13 s | 2 s (saving, figures) | 14 s | 0.51 GB |
| miMic | cached (0 s) | 31 s | 31 s | 0.71 GB |
| iMic | cached (0 s) | 16 s | 16 s | 0.55 GB |
| GIMIC | cached (0 s) | 45 s | 45 s | 0.76 GB |

## mimic-257

257 samples, 263 taxa → 172 features.

| Tool | Preprocessing | Tool itself | Total | Peak memory |
|---|---|---|---|---|
| MIPMLP (just preprocess) | 15 s | 2 s (saving, figures) | 17 s | 0.51 GB |
| miMic | cached (0 s) | 54 s | 54 s | 0.72 GB |
| iMic | cached (0 s) | 33 s | 33 s | 0.58 GB |
| GIMIC | cached (0 s) | 1.9 min | 1.9 min | 0.77 GB |

## FRANZOSA-220

220 samples, 55,882 taxa → 44,195 features; 8,848 metabolites.

| Tool | Preprocessing | Tool itself | Total | Peak memory |
|---|---|---|---|---|
| MIPMLP (just preprocess) | 14.9 min | 5.2 min (saving, figures) | 20.2 min | 1.57 GB |
| miMic | cached (0 s) | **> 60 min** (stopped) | **> 60 min** | at least 8.79 GB |
| iMic | cached (0 s) | **> 60 min** (stopped) | **> 60 min** | at least 2.08 GB |
| GIMIC | cached (0 s) | **> 60 min** (stopped) | **> 60 min** | at least 8.79 GB |
| LOCATE | 13.4 min | 4.7 min | 18.1 min | 1.58 GB |

## YACHIDA-347

347 samples, 57,702 taxa → 43,166 features; 450 metabolites.

| Tool | Preprocessing | Tool itself | Total | Peak memory |
|---|---|---|---|---|
| MIPMLP (just preprocess) | 12.6 min | 6.8 min (saving, figures) | 19.4 min | 2.19 GB |
| miMic | cached (0 s) | **> 60 min** (stopped) | **> 60 min** | at least 7.46 GB |
| iMic | cached (0 s) | **> 60 min** (stopped) | **> 60 min** | at least 2.36 GB |
| GIMIC | cached (0 s) | **> 60 min** (stopped) | **> 60 min** | at least 7.69 GB |
| LOCATE | 21.8 min | 7.9 min | 29.7 min | 2.19 GB |

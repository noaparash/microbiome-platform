# miMic authors' example data (unchanged)

`for_process.csv` and `tag.csv` are copied byte for byte from
https://github.com/oshritshtossel/miMic/tree/master/example_data (LGPL-3.0):
257 samples × 263 ASVs of raw counts with a `taxonomy` row, and binary labels.

Used by `tests/test_reproduction.py`, which runs miMic exactly as the authors'
`example_use.py` does and checks that our engine gives identical results.

# GIMIC authors' example data (unchanged)

`for_preprocess.csv` and `tag.csv` are copied unchanged from
https://github.com/oshritshtossel/SAMBA/tree/main/example_data:
257 samples × 4,957 ASVs of raw counts with a `taxonomy` row; labels in `Tag`
(plus a `Group` column, which is not used).

Used by `tests/test_reproduction.py`: running SAMBA's `example_use.py` steps
(`MIPMLP.preprocess(df)` with its defaults, i.e. mean grouping, then
`micro2matrix` and `build_SAMBA_distance_matrix`) must give exactly the distance
matrix our GIMIC engine gives in mean mode.

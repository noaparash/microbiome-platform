# Test data

A small, balanced slice of the example data from the authors' miMic repository
(https://github.com/oshritshtossel/miMic, `example_data/`, LGPL-3.0):

- `example_counts.csv`: 40 samples × 263 ASVs of raw counts. The first column
  is `ID` and the last row is `taxonomy`, which is the shared input format.
- `example_tag.csv`: binary labels in a `Tag` column, 20 per class.

Rows were drawn with `groupby("Tag").sample(20, random_state=0)`.
Replace this with real lab data when it becomes available.

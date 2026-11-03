# User guide

For researchers using the website. No programming needed.

## Start the website (on your own computer)

In VS Code: **Terminal → New Terminal**, then:

```powershell
.venv\Scripts\flask.exe --app microplatform.web run
```

Wait for `Running on http://127.0.0.1:5000`, open that address in your
browser, and keep the terminal open. To stop the website, press **Ctrl+C** in the
terminal.

## An analysis in four steps

1. **Upload.** On the home page you can pick your question ("Which bacteria
   differ between my groups?"). The upload box then names the files that
   question needs. Drop your files: which one is the counts table, the labels
   file or the metabolite table is detected automatically.
2. **Data check.** You see what was found: samples, taxa, taxonomy depth,
   sparsity, read depth and label type. Red problems block the analysis and
   say how to fix them. Amber warnings (for example, a sample with far more
   reads than the rest) do not block it.
3. **Plan.** A task is recommended, with the reasons. You can choose
   another. If a task needs a file you have not uploaded, it says which one,
   and you can add a labels file or a metabolite table right there.
4. **Results.** After you click Run, the analysis runs on the server and the
   page shows "Running…". You can close the page: it updates by itself, and
   the link shown there brings you back to the results at any time. When it is
   done you get a summary, figures, the processed table and a record of every
   setting used. (If the lab has switched email on, you can also leave your
   address to receive the link; it is deleted once the email is sent.)

## Which files each task needs

| Task | Tool | Files |
|---|---|---|
| Just preprocess | MIPMLP | counts table |
| Find bacteria that differ between groups | miMic | counts + labels (two groups, or a continuous label) |
| Predict the outcome | iMic | counts + labels (two groups) |
| See how samples group | GIMIC | counts (labels optional, for colouring) |
| Link bacteria to metabolites | LOCATE | counts + metabolite table (at least 20 samples in both) |

## File formats

**Counts table** (CSV or TSV): one row per sample, one column per bacterium.
The first column holds the sample IDs (named `ID`), and the **last row** is
named `taxonomy` and holds each column's lineage.

```
ID,       ASV1,          ASV2,          …
sample1,  120,           0,             …
sample2,  37,            5,             …
taxonomy, k__Bacteria;…, k__Bacteria;…, …
```

**Labels file** (optional): sample IDs in the first column, and the outcome in
a column named `Tag`. Binary (sick/healthy), categorical (a few groups) and
continuous (a number such as age) are all recognised.

```
ID,      Tag
sample1, 1
sample2, 0
```

**Metabolite table** (optional, for linking bacteria to metabolites): sample
IDs in the first column, the same as in the counts table, then one column per
metabolite with the measured concentrations or intensities. Do not
log-transform them: 0 means "not detected", and the platform normalises the
values the way the LOCATE paper does. A table is recognised as metabolites
when it has at least 3 numeric columns and no `Tag` column.

```
ID,      Acetate, Butyrate, …
sample1, 5210.4,  830.2,    …
sample2, 4480.0,  0,        …
```

Templates of all three are on the website (in every error message, and under
"What should my files look like?"). Excel files must be saved as CSV first
(File → Save As → CSV UTF-8).

## What you get

- **The processed table** (CSV): MIPMLP's output, one row per sample.
- **Figures**: each as PNG, SVG (with editable text) and an interactive HTML
  file that works offline, each with a CSV of the exact data plotted.
- **"Download everything"**: one ZIP with a README, the reproducibility
  record (every setting and version), the results, the figures and your input
  files.
- **A data overview**, the same for every task, at the end of the results. It
  holds the standard figures that describe a microbiome dataset. They are
  **descriptive, not statistical tests**: a difference you see there is not
  evidence by itself.
  - **Composition of each sample:** a stacked bar per sample, in % of its
    reads, by phylum. The 7 most abundant phyla get a colour; the rest are
    "Other". With a labels file, samples are grouped by label, with an
    average bar per group.
  - **Average composition:** a pie, one per group. The colours match the bars.
  - **Alpha diversity:** Shannon index and richness, as a box per group with
    every sample shown.
  - **Beta diversity:** a PCoA map of Bray-Curtis distances, coloured by
    group.
  - **Sparsity:** taxa detected per sample (rows) and in how many samples each
    taxon appears (columns).

  All of these are computed from your raw counts, not from the
  log-transformed table the tools use, so composition always adds up to 100%.
  Taxon colours come from the Okabe-Ito palette, which stays distinguishable
  for colour-blind readers.

## How good are LOCATE's predictions?

LOCATE's results report **one training run**, which is what you can expect in
practice: the median correlation between measured and predicted metabolite
levels on held-out samples. The LOCATE paper's per-dataset figures show, for
each metabolite, the best of 16 runs. On two of the paper's public datasets
that made the median about 0.13 higher (FRANZOSA: 0.37 for one run vs 0.50
best-of-16; YACHIDA: 0.14 vs 0.28), so expect lower numbers here than in the
paper's figures. Details: `validation/locate/`.

## Try it without data

Use **Example** in the top menu: a 40-sample slice of the miMic authors'
example data. Its data check flags one real oddity: sample a498 has about
10 million reads, 90% of them from one genus.

## Citing

The results ZIP lists the papers for the methods used. They are also on the
**Methods** and **About** pages.

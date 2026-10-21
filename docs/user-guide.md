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
   question needs. Drop your files: which one is the counts table and which is
   the labels file is detected automatically.
2. **Data check.** You see what was found: samples, taxa, taxonomy depth,
   sparsity, read depth and label type. Red problems block the analysis and
   say how to fix them. Amber warnings (for example, a sample with far more
   reads than the rest) do not block it.
3. **Plan.** A task is recommended, with the reasons. You can choose
   another. If a task needs a file you have not uploaded, it says which one,
   and you can add a labels file right there.
4. **Results.** A summary, figures, the processed table and a record of every
   setting used. Each analysis has its own link: bookmark it to come back.

## Which files each task needs

| Task | Tool | Files |
|---|---|---|
| Just preprocess | MIPMLP | counts table |
| Find bacteria that differ between groups | miMic | counts + labels (two groups, or a continuous label) |
| Predict the outcome | iMic *(coming next)* | counts + labels |
| See how samples group | GIMIC *(planned)* | counts |
| Link bacteria to metabolites | LOCATE *(planned)* | counts + metabolite table |

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

Templates of both are on the website (in every error message, and under
"What should my files look like?"). Excel files must be saved as CSV first
(File → Save As → CSV UTF-8).

## What you get

- **The processed table** (CSV): MIPMLP's output, one row per sample.
- **Figures**: each as PNG, SVG (with editable text) and an interactive HTML
  file that works offline, each with a CSV of the exact data plotted.
- **"Download everything"**: one ZIP with a README, the reproducibility
  record (every setting and version), the results, the figures and your input
  files.

## Try it without data

Use **Example** in the top menu: a 40-sample slice of the miMic authors'
example data. Its data check flags one real oddity: sample a498 has about
10 million reads, 90% of them from one genus.

## Citing

The results ZIP lists the papers for the methods used. They are also on the
**Methods** and **About** pages.

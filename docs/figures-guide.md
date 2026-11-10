# Guide to every figure and table

A presenter's script for the Microbiome Platform's results pages: for each figure and table,
what it shows, its axes and units, how to read it, and whether it is **descriptive** (just
showing the data) or a **statistical test** (a yes/no question answered with a p-value).

**Before you start, three ideas the audience needs:**
- **The data.** Each *sample* (for example, one person's stool) was sequenced, and the
  sequencer counted how many *reads* (DNA fragments) came from each *taxon* (a type of
  bacterium). Taxa are named along a *taxonomic tree*: Kingdom → Phylum → Class → Order →
  Family → Genus → Species.
- **A label** is what we know about each sample (for example, sick / healthy). Some tools
  need it, some don't.
- **The page order** is always: the tool's result first, then data-quality checks, then a
  descriptive overview of the data (the same for every tool).

**The labels used below:**
- **Descriptive:** a picture of the data; nothing is tested.
- **Statistical test:** the tool's own test, with a p-value. p < 0.05 is the usual cut-off for
  "unlikely to be chance".
- **Exploratory test:** a test the platform adds for orientation. It is not corrected across the
  whole report and is not the tool's finding.
- **Model performance:** how well a trained model predicts samples it did not learn from. This
  is a measured score, not a test.

---

## 1. The shared data overview (every run)

### Sequencing depth per sample (data quality)
- **What it shows:** how many reads each sample has in total, one bar per sample, highest to lowest.
  More reads = the sample was "looked at" more closely.
- **Axes:** x = the samples, sorted by depth (no unit). y = total reads, a count, on a **log
  scale** (each grid step is ×10), because depths often range from thousands to millions.
- **How to read it:** look for bars far below the rest (a likely failed sample) or far above
  (possible contamination). A smooth staircase is healthy.
- **Type:** descriptive. Shown only when the upload is raw read counts.

### Composition of each sample (phylum), the stacked bars
- **What it shows:** what each sample is made of, at the phylum level (the broad bacterial
  groups). Left panel: one bar per sample. Right panel: the average of all samples.
- **Axes:** x = the samples (no unit), sorted by Firmicutes, most first. y = **relative
  abundance in %**: each bar adds up to 100%. Percentages are used because samples have
  different numbers of reads, so only shares can be compared.
- **How to read it:** the 12 most abundant phyla have their own colour; the rest are grey
  "Other". Look for samples that look very different from the average bar.
- **Type:** descriptive. Made from the uploaded table, not the transformed table the tools use.

### Average composition (phylum), the pie(s)
- **What it shows:** the average share of each phylum: one pie for all samples, or one pie per
  group when the data has labels. Each sample counts equally.
- **Axes:** no axes. Each slice's angle is its **share in %** of the average sample. Slices of
  5% or more are labelled.
- **How to read it:** compare the pies of the groups. Colours match the stacked bars, so a
  phylum keeps one colour everywhere.
- **Type:** descriptive.

### Diversity within each sample (alpha diversity)
- **What it shows:** how varied each sample is, in two panels. **Shannon index** grows with both
  the number of taxa and how evenly they are spread. **Richness** is simply how many taxa the
  sample contains.
- **Axes:** x = the groups (or "all samples"). y, left panel = Shannon index, a unitless number
  (natural log, typically 0 to 5). y, right panel = richness, a count of taxa.
- **How to read it:** each dot is a sample, the box covers the middle half of the samples, and
  the line in it is the median. Higher = more diverse. Richness is counted on raw reads without
  rarefaction (subsampling every sample to the same depth), so deeper samples tend to show more
  taxa.
- **Type:** descriptive. With groups, the brackets add an **exploratory test** (stars:
  * p < 0.05, ** < 0.01, *** < 0.001, ns = not significant). The test used is named above each
  panel, and every p-value is in "Tests (CSV)".

### How similar samples are (beta diversity, PCoA)
- **What it shows:** a map of the samples where samples with similar compositions sit close
  together. It is built from the Bray-Curtis difference between every pair of samples
  (0 = identical, 1 = nothing in common).
- **Axes:** x = PCo1 and y = PCo2. These are directions in the data with **no unit**; only
  distances between points matter. Each axis title says what % of the differences between
  samples that axis captures.
- **How to read it:** look for clusters and outliers. With groups, points are coloured and
  each dashed ellipse marks where about 95% of a group would fall. Separated ellipses = groups
  that differ in composition.
- **Type:** descriptive. With groups, it adds an **exploratory test** (PERMANOVA: "do the groups
  differ in composition?"). Its p-value and the share of variation between groups are in the
  subtitle; the details are in "Tests (CSV)".

### How many taxa each sample contains (row sparsity)
- **What it shows:** for each sample, how many of the table's taxa appear in it at all. Most
  taxa are absent from most samples; this shows how many are present.
- **Axes:** x = taxa detected in a sample (a count). y = number of samples (a count). It's a
  histogram: each bar collects samples with a similar number of taxa.
- **How to read it:** the dashed line is the median. A sample far to the left of the rest has
  unusually few taxa: possibly a failed sample.
- **Type:** descriptive.

### How widespread each taxon is (column sparsity)
- **What it shows:** for each taxon, in what share of the samples it appears.
- **Axes:** x = present in % of samples (0 to 100%). y = number of taxa (a count). It's a
  histogram.
- **How to read it:** a tall bar near 0% is normal: most taxa are rare. The dashed line is
  MIPMLP's cut-off; taxa found in fewer than 1% of samples are dropped before the analysis.
- **Type:** descriptive.

### The tests tables ("Tests (CSV)", alpha and beta)
- **What it shows:** the numbers behind the brackets and the PERMANOVA subtitle: one row per
  comparison.
- **Columns:** the groups compared and their sizes, the test used, its statistic, the p-value
  and the FDR-corrected p-value, and the effect size (alpha: Cohen's d). Beta adds PERMANOVA's
  pseudo-F, R², η² and PERMDISP (which checks whether the groups differ in spread rather than
  position).
- **How to read it:** use `p_fdr` (corrected for the number of comparisons), not the raw p.
- **Type:** exploratory test.

---

## 2. MIPMLP: the processed (cleaned) table

### The processed table (download "Processed table")
- **What it shows:** the uploaded counts, cleaned the way the MIPMLP paper recommends. It is the
  shared starting point every other tool analyses. One row per sample, one column per feature.
- **Columns and units:** each column name is a taxon's lineage (Kingdom;Phylum;…). Values are
  **log10(reads + 0.1)**, so one unit = tenfold more reads. Log is used because counts span many
  orders of magnitude, and the MIPMLP paper found it works best.
- **How to read it:** related taxa are merged with sub-PCA. A name ending `_0`, `_1` is the 1st,
  2nd summary component of a group, which is why some values are negative. Very rare taxa are
  removed, and `else` collects leftovers.
- **Type:** descriptive (a data transformation, no test). It's the input to the analyses, not a
  finding.

---

## 3. miMic: which bacteria differ between groups?

### miMic's cladogram (the tree)
- **What it shows:** the taxonomic tree of the bacteria miMic found, drawn by miMic itself. The
  centre is the top of the tree (Kingdom), and the branches go out to the species.
- **Axes:** none; it's a circular tree. Marker colour: blue = higher in one group, red = higher
  in the other (the caption names which). Marker size grows with significance, up to a cap. Background colour
  = the taxon's family.
- **How to read it:** look at where the markers cluster. A whole branch of one colour means a
  related set of bacteria moves together. Shapes: sphere = found by both miMic's tree test and
  the per-taxon test, circle = the tree test only, square = the per-taxon test only (not counted
  as miMic's result).
- **Type:** statistical test (miMic's result, p < 0.05 with miMic's correction among sister taxa).

### Bacteria that differ between the groups (bar chart)
- **What it shows:** the significant taxa (up to 25, most significant at the top), each with its
  direction and strength.
- **Axes:** y = the taxa. x = **miMic's score**: a Mann-Whitney U statistic centred at 0, so it
  has no unit. To the right = higher in the group named on the axis; to the left = higher in the other.
  For a numeric label, x is instead a Spearman correlation (from −1 to 1).
- **How to read it:** longer bar = stronger difference. The score grows with the number of
  samples, so compare bars within one chart, never between datasets. For p-values, use the
  table.
- **Type:** statistical test (miMic's result).

### Is miMic's result more than chance? (RP vs SP)
- **What it shows:** miMic re-runs its tree test starting from each level of the tree, once with
  the real labels (teal, "RP") and once with the labels shuffled at random (orange, "SP"). It
  counts how many leaves come out significant each time.
- **Axes:** y = the level the tree test starts at (Kingdom … Species, plus "<level> & leaves").
  x = the number of significant leaves, a count, on a plain scale with each count written on its
  bar.
- **How to read it:** real counts far above shuffled counts mean the findings are unlikely to be
  chance.
  - The **grey row** is the level miMic's own result started from, so its count equals the
    headline.
  - The "**& leaves**" row adds the taxa found only by the per-taxon test (e.g. 14 + 6 = 20).
  - Other rows start elsewhere, so their counts differ by design.
  - *Note:* the legend currently calls the grey band "Passed the a-priori test"; that label is
    being corrected. Present it as "where miMic's result starts".
- **Type:** a check computed by miMic from one shuffle: counts, not a p-value, so not itself a
  statistical test.

### The significant-taxa table ("Most significant taxa (miMic)")
- **What it shows:** every taxon miMic found, most significant first. Two companion downloads:
  "leaf test only" (taxa found only by testing each taxon on its own; not miMic's result) and
  "apriori_test" (miMic's first gate, explained below).
- **Columns:** name; statistic (miMic's score, as in the bar chart); p-value; direction ("higher
  in …"); found by (tree path / tree path and leaf test / leaf test only).
- **How to read it:** each row is one finding. The smaller the p-value, the stronger the evidence.
- **The a-priori table:** one row per taxonomic level, with miMic's first test (does the label
  relate to the microbiome at all?). It shows p, −log10(p) (bigger = stronger) and a
  significant yes/no. If no level passes, miMic stops there.
- **Type:** statistical test (miMic's result; the a-priori table is miMic's gate test).

---

## 4. iMic: can the microbiome predict the label?

### ROC curve on the test samples (AUC in the title)
- **What it shows:** how well iMic tells the two groups apart. It is measured on the 20% of
  samples held back from training (the "test samples").
- **Axes:** x = false positive rate: the fraction (0 to 1) of the other group wrongly called
  positive. y = true positive rate: the fraction (0 to 1) of the target group correctly caught.
  Fractions are used so different datasets compare on one 0-to-1 scale.
- **How to read it:** each point is a different cut-off for calling a sample positive. The
  dashed diagonal is guessing. A curve hugging the top-left corner is good. **AUC** sums the curve
  up: 0.5 = chance, 1 = perfect.
- **Type:** model performance (one random split of the samples, not a statistical test). With
  few test samples it is a rough estimate.

### The predictions table
- **What it shows:** iMic's prediction for every sample.
- **Columns:** sample; set (test or train); true group; probability of the target group (0 to 1);
  predicted group (the group with probability above 0.5).
- **How to read it:** judge iMic only on the **test** rows. The train rows are samples it learned
  from, so they look better than reality.
- **Type:** model performance.

### Test metrics table
- **What it shows:** the summary scores on the test samples.
- **Columns:** number of test samples; AUC; accuracy (share predicted correctly); balanced
  accuracy (the average of the two groups' accuracies, fair when groups are unequal in size).
- **How to read it:** all scores run from 0 to 1. Balanced accuracy of 0.5 = guessing.
- **Type:** model performance.

---

## 5. GIMIC: how do the samples group?

### Map of the samples (UMAP of GIMIC distances)
- **What it shows:** every sample as a point, placed so that samples with similar microbiomes
  are close. GIMIC compares samples as pictures of their taxonomic tree.
- **Axes:** "Map dimension 1" and "Map dimension 2" have **no units and no meaning of their
  own**. UMAP only tries to keep similar samples near each other, so only closeness matters.
  Points are coloured by label when there is one.
- **How to read it:** look for clusters and outliers. Distances on the map are approximate; the
  exact ones are in the distance-matrix table.
- **Type:** descriptive.

### Distances within and between groups (bar chart, with labels)
- **What it shows:** the average GIMIC distance between two samples of the same group, and
  between two samples of different groups.
- **Axes:** x = the comparison (within each group, between groups). y = average GIMIC distance,
  an **angle in radians**: 0 = identical; larger = more different.
- **How to read it:** if "between groups" is clearly higher than "within", samples resemble
  their own group more. The summary gives the ratio (e.g. 1.14×).
- **Type:** descriptive (no test).

### The tables: distance matrix, map coordinates, group distances
- **Distance matrix:** a sample × sample grid of GIMIC distances, in radians. The diagonal is 0
  (each sample vs itself). This is GIMIC's main output, for further analysis.
- **Map coordinates:** each sample's two map positions and its group. They are the numbers
  behind the map and have no units.
- **Group distances:** the bar chart's numbers, plus how many pairs each average is based on.
- **Type:** descriptive.

---

## 6. LOCATE: can the microbiome predict metabolites?

### Best-predicted metabolites (bar chart)
- **What it shows:** for the 20 best-predicted metabolites, how well LOCATE predicted their
  levels from the microbiome. It is measured on test samples LOCATE did not learn from.
- **Axes:** y = the metabolites. x = Spearman correlation between measured and predicted levels,
  from −1 to 1 and unitless. Spearman compares rankings: does the sample with the most of a
  metabolite also get the highest prediction?
- **How to read it:** 1 = the predictions put the samples in exactly the right order, 0 = no
  relation, below 0 = the wrong direction. It is one training run; the paper's figures keep the
  best of 16 runs, so they look better.
- **Type:** model performance.

### Metabolite scores table
- **What it shows:** every metabolite's score, best first.
- **Columns:** metabolite; Spearman correlation (as above); p, Spearman's own p-value for that
  one metabolite.
- **How to read it:** the p-values are **not corrected** for testing many metabolites at once.
  With hundreds of metabolites, some will look significant by chance, so use them as a guide
  only.
- **Type:** model performance (the per-metabolite p is an uncorrected test).

### Predicted metabolites (test samples) table
- **What it shows:** LOCATE's predicted level of every metabolite, for every test sample.
- **Units:** **z-scores** of the log of each metabolite's relative amount. 0 = an average sample,
  +1 = one standard deviation above average. This is the scale LOCATE is trained on, as in the
  paper.
- **How to read it:** compare with the measured values (on the same scale) to see where the
  model succeeds. Don't read the values as concentrations.
- **Type:** model performance (predictions).

### Latent representation table
- **What it shows:** LOCATE's internal summary of each sample: 10 numbers (z1 … z10) it learned
  to connect bacteria to metabolites, for training and test samples.
- **Units:** none; these are internal coordinates.
- **How to read it:** for advanced users: e.g. for clustering samples or for further modelling.
  It is not meant to be interpreted by eye.
- **Type:** descriptive (a model output, not a test).

---

*Every figure on the site also has "Method details" (under its caption) and downloads: PNG, SVG,
an interactive version and the data CSV. The results ZIP lists every figure's caption and
details in `figures/FIGURES.txt`.*

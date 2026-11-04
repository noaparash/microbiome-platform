from pathlib import Path
import os, glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch

# ===== SETTINGS =====
BASE_DIR = Path(__file__).resolve().parent
input_folder = BASE_DIR / "datasets_after_MIPMLP"
output_folder = BASE_DIR / "1B_plots/16S"
os.makedirs(output_folder, exist_ok=True)

top_n = 12

# ===== LOAD FILES =====
csv_files = sorted(glob.glob(os.path.join(input_folder, "*_16S_formatted.csv")))

# Omri is PRJEB58050 and is already included above under its current name.
# Do not load the legacy omri/ tables as an additional dataset.

if not csv_files:
    raise FileNotFoundError(f"No formatted abundance tables found in {input_folder}")
print(f"Found {len(csv_files)} CSV files")

data = {}

for f in csv_files:
    file_name = os.path.splitext(os.path.basename(f))[0]
    rel = pd.read_csv(f, index_col=0)

    # clean column names, just in case
    rel.columns = rel.columns.astype(str).str.strip()
    rel.columns = rel.columns.str.replace(r"\s*;\s*", ";", regex=True)

    # Option: drop "Bacteria" and "Unassigned" if they exist, then re-normalize
    rel = rel.drop(columns=["Bacteria", "Archaea", "Unassigned", "Unclassified"], errors="ignore")
    # Standardize phylum labels with or without taxonomy rank prefixes.
    rel.columns = [c.split(";")[-1].removeprefix("p__") for c in rel.columns]
    rel = rel.T.groupby(level=0, sort=False).sum().T
    if not np.isfinite(rel.to_numpy(dtype=float)).all() or (rel < 0).any().any():
        raise ValueError(f"Invalid abundance values in {f}")
    valid = rel.sum(axis=1) > 0
    if not valid.all():
        print(f"Dropping {(~valid).sum()} zero-sum samples from {file_name}")
    rel = rel.loc[valid]
    if rel.empty:
        raise ValueError(f"No nonzero phylum abundances in {f}")
    rel = rel.div(rel.sum(axis=1), axis=0) * 100


    data[file_name] = rel

# ===== GLOBAL TAXA ORDER =====
combined = pd.concat(data.values(), axis=0).fillna(0)

global_order = (
    combined.mean(axis=0)
    .sort_values(ascending=False)
    .head(top_n)
    .index
    .tolist()
)

print("Global taxa order:")
for t in global_order:
    print(t)

# ===== GLOBAL COLOR MAP =====
colors = (
    list(plt.cm.tab20.colors) +
    list(plt.cm.Set3.colors) +
    list(plt.cm.Pastel1.colors)
)

global_color_map = {t: colors[i % len(colors)] for i, t in enumerate(global_order)}
global_color_map["Other"] = "#BDBDBD"

# ===== MAIN LOOP =====
all_records = []

for file_name, rel in data.items():
    print(f"\nProcessing: {file_name}")

    group = (
        "Control" if "Control" in file_name
        else "Pregnant" if "Pregnant" in file_name
        else "Unknown"
    )

    # use the same taxa order in every file
    taxa_in_file = [t for t in global_order if t in rel.columns]
    rel_top = rel[taxa_in_file].copy()

    other_taxa = [c for c in rel.columns if c not in global_order]
    if other_taxa:
        rel_top["Other"] = rel[other_taxa].sum(axis=1)

    # fixed column order: global taxa first, Other last
    final_order = taxa_in_file + (["Other"] if "Other" in rel_top.columns else [])
    rel_top = rel_top[final_order]

    # sort samples like original code
    if "Firmicutes" in rel_top.columns:
        rel_top = rel_top.sort_values(by="Firmicutes", ascending=False)
    else:
        rel_top = rel_top.sort_values(by=rel_top.columns[0], ascending=False)

    for taxon in taxa_in_file:
        all_records.append(pd.DataFrame({
            "dataset": file_name,
            "group": group,
            "taxon": taxon,
            "value": rel[taxon].values
        }))

    color_map = {t: global_color_map[t] for t in rel_top.columns}

    # ===== STACKED BAR PLOT =====
    fig, axes = plt.subplots(
        1, 2,
        figsize=(16, 6),
        gridspec_kw={"width_ratios": [5, 1]}
    )

    ax_samples, ax_mean = axes

    x_positions = range(len(rel_top))
    bottom = np.zeros(len(rel_top))

    for taxon in rel_top.columns:
        values = rel_top[taxon].values
        ax_samples.bar(
            x_positions,
            values,
            bottom=bottom,
            width=0.9,
            color=color_map[taxon],
            edgecolor="none"
        )
        bottom += values

    ax_samples.set_ylabel("Relative abundance (%)", fontsize=12)
    ax_samples.set_ylim(0, 100)
    ax_samples.set_xticks([])
    ax_samples.set_title("Samples", fontsize=13)
    ax_samples.spines["top"].set_visible(False)
    ax_samples.spines["right"].set_visible(False)

    mean_values = rel_top.mean(axis=0)
    bottom = 0

    for taxon in rel_top.columns:
        ax_mean.bar(
            [0],
            [mean_values[taxon]],
            bottom=bottom,
            width=0.9,
            color=color_map[taxon],
            edgecolor="none"
        )
        bottom += mean_values[taxon]

    ax_mean.set_ylim(0, 100)
    ax_mean.set_xticks([0])
    ax_mean.set_xticklabels(["Mean"], fontsize=11)
    ax_mean.set_title("Average", fontsize=13)
    ax_mean.spines["top"].set_visible(False)
    ax_mean.spines["right"].set_visible(False)
    ax_mean.spines["left"].set_visible(False)
    ax_mean.yaxis.set_visible(False)

    handles = [
        Rectangle((0, 0), 1, 1, color=color_map[t], label=t)
        for t in rel_top.columns
    ]

    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=4,
        frameon=False,
        fontsize=9
    )

    fig.suptitle(file_name, fontsize=16, fontweight="bold")
    plt.tight_layout(rect=[0, 0.12, 1, 1])

    out_path = os.path.join(output_folder, f"{file_name}_phylum_composition.png")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Saved stacked plot to: {out_path}")


# ===== COMBINED SPLIT VIOLIN PLOT =====
if all_records:
    violin_df = pd.concat(all_records, ignore_index=True)
    violin_df = violin_df[violin_df["group"].isin(["Control", "Pregnant"])]

    # same order as stacked plots
    taxon_order = [t for t in global_order if t in violin_df["taxon"].unique()]

    fig, ax = plt.subplots(figsize=(max(14, len(taxon_order) * 0.8), 7))

    control_color = "#4C72B0"
    pregnant_color = "#DD8452"

    for i, taxon in enumerate(taxon_order):
        for group, side, color in [
            ("Control", "left", control_color),
            ("Pregnant", "right", pregnant_color),
        ]:
            vals = violin_df[
                (violin_df["taxon"] == taxon) &
                (violin_df["group"] == group)
            ]["value"].dropna().values

            if len(vals) > 1:
                parts = ax.violinplot(
                    [vals],
                    positions=[i],
                    widths=0.8,
                    showmeans=False,
                    showmedians=True,
                    showextrema=False
                )

                for body in parts["bodies"]:
                    body.set_facecolor(color)
                    body.set_edgecolor("black")
                    body.set_alpha(0.7)

                    verts = body.get_paths()[0].vertices
                    if side == "left":
                        verts[:, 0] = np.minimum(verts[:, 0], i)
                    else:
                        verts[:, 0] = np.maximum(verts[:, 0], i)

                if "cmedians" in parts:
                    parts["cmedians"].set_color("black")
                    parts["cmedians"].set_linewidth(1.2)

    ax.set_xticks(range(len(taxon_order)))
    ax.set_xticklabels(taxon_order, rotation=45, ha="right")
    ax.set_ylabel("Relative abundance (%)")
    ax.set_title("Top phyla across 16S datasets: Control vs Pregnant")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.legend(handles=[
        Patch(facecolor=control_color, edgecolor="black", label="Control"),
        Patch(facecolor=pregnant_color, edgecolor="black", label="Pregnant")
    ], frameon=False)

    plt.tight_layout()

    violin_out = os.path.join(output_folder, "violin_plot_16S.png")
    plt.savefig(violin_out, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Saved combined split violin plot to: {violin_out}")

print("Done.")

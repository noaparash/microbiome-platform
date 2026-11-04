from pathlib import Path
import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch
import numpy as np

# ===== SETTINGS =====
BASE_DIR = Path(__file__).resolve().parent
input_folder = BASE_DIR / "datasets_after_yamas/SG"
output_folder = BASE_DIR / "1B_plots/SG"
os.makedirs(output_folder, exist_ok=True)

sample_id_col = "SampleID"
group_col = "Group"
top_n = 12   # keep top phyla per dataset, merge the rest into "Other" in the stacked plots


def extract_phylum(taxon_name):
    """
    Extract phylum level from taxonomy string.
    Example:
    k__Bacteria,p__Firmicutes,c__Clostridia -> Bacteria;Firmicutes
    """
    parts = str(taxon_name).split(",")
    kingdom = None
    phylum = None

    for part in parts:
        part = part.strip()
        if part.startswith("k__"):
            kingdom = part.replace("k__", "")
        elif part.startswith("p__"):
            phylum = part.replace("p__", "")

    if phylum:
        if kingdom:
            return f"{kingdom};{phylum}"
        return phylum

    return None


def prepare_relative_phylum_table(df, sample_id_col, group_col, file_name=""):
    """
    Prepare relative abundance table at phylum level for one dataset.
    Returns:
        rel    -> relative abundance table (%)
        groups -> group labels per sample
    """
    # Rename first column if needed
    if df.columns[0] != sample_id_col:
        df = df.rename(columns={df.columns[0]: sample_id_col})

    if group_col not in df.columns:
        labels = [g for g in ("Control", "Pregnant") if g in file_name.split("_")]
        if len(labels) != 1:
            raise ValueError(f"Cannot infer group from {file_name}")
        df = df.copy()
        df[group_col] = labels[0]

    df = df.set_index(sample_id_col)

    # Keep group separately before numeric filtering
    groups = df[group_col].astype(str).str.strip()

    # Keep numeric columns only
    abundance = df.select_dtypes(include="number").copy()

    if abundance.shape[1] == 0:
        return None, None

    # Remove zero-sum samples
    row_sums = abundance.sum(axis=1)
    valid_mask = row_sums > 0
    abundance = abundance.loc[valid_mask]
    groups = groups.loc[valid_mask]

    if abundance.empty:
        return None, None

    # Collapse to phylum level
    phylum_map = {}
    for col in abundance.columns:
        # These MetaPhlAn tables contain all ranks. Use only phylum rows
        # (transposed to columns), so descendants are not counted again.
        if not str(col).split(",")[-1].strip().startswith("p__"):
            continue
        phylum = extract_phylum(col)
        if phylum is not None:
            phylum_map[col] = phylum

    if len(phylum_map) == 0:
        return None, None

    abundance_phylum = abundance[list(phylum_map.keys())].copy()
    abundance_phylum.columns = [phylum_map[c] for c in abundance_phylum.columns]

    # Merge duplicate phylum columns by summing
    abundance_phylum = abundance_phylum.T.groupby(level=0).sum().T

    # Convert to relative abundance (%)
    if not np.isfinite(abundance_phylum.to_numpy()).all() or (abundance_phylum < 0).any().any():
        raise ValueError(f"Invalid phylum abundances in {file_name}")
    valid = abundance_phylum.sum(axis=1) > 0
    abundance_phylum = abundance_phylum.loc[valid]
    groups = groups.loc[valid]
    if abundance_phylum.empty:
        return None, None
    rel = abundance_phylum.div(abundance_phylum.sum(axis=1), axis=0) * 100

    return rel, groups


csv_files = sorted(glob.glob(os.path.join(input_folder, "*_SG_formatted.csv")))
if not csv_files:
    raise FileNotFoundError(f"No formatted abundance tables found in {input_folder}")
print(f"Found {len(csv_files)} CSV files")

# ===== BUILD GLOBAL COLOR MAP =====
all_top_taxa = []

for file_path in csv_files:
    file_name = os.path.splitext(os.path.basename(file_path))[0]
    print(f"Scanning for colors: {file_name}")

    df = pd.read_csv(file_path)
    rel, groups = prepare_relative_phylum_table(df, sample_id_col, group_col, file_name)

    if rel is None:
        print(f"Skipping {file_name} in color-map stage")
        continue

    phylum_means = rel.mean(axis=0).sort_values(ascending=False)
    top_phyla = phylum_means.head(top_n).index.tolist()
    all_top_taxa.extend(top_phyla)

# unique taxa in stable order
global_taxa_order = list(dict.fromkeys(all_top_taxa))

colors = (
    list(plt.cm.tab20.colors) +
    list(plt.cm.Set3.colors) +
    list(plt.cm.Pastel1.colors)
)

global_color_map = {
    taxon: colors[i % len(colors)]
    for i, taxon in enumerate(global_taxa_order)
}

# Make "Other" always gray
global_color_map["Other"] = "#BDBDBD"

# ===== MAIN LOOP =====
all_records = []

for file_path in csv_files:
    file_name = os.path.splitext(os.path.basename(file_path))[0]
    title_name = file_name.split("_")[0]

    print(f"Processing: {file_name}")

    df = pd.read_csv(file_path)
    rel, groups = prepare_relative_phylum_table(df, sample_id_col, group_col, file_name)

    if rel is None:
        print(f"Skipping {file_name}: could not prepare relative phylum table")
        continue

    # ===== KEEP TOP PHYLA FOR THIS DATASET =====
    phylum_means = rel.mean(axis=0).sort_values(ascending=False)
    top_phyla = phylum_means.head(top_n).index.tolist()

    # --------- collect records for combined violin ----------
    for taxon in top_phyla:
        tmp = pd.DataFrame({
            "dataset": title_name,
            "group": groups.values,
            "taxon": taxon,
            "value": rel[taxon].values
        })
        all_records.append(tmp)

    # ===== STACKED PLOT FOR THIS DATASET =====
    rel_top = rel[top_phyla].copy()

    other_phyla = [c for c in rel.columns if c not in top_phyla]
    if other_phyla:
        rel_top["Other"] = rel[other_phyla].sum(axis=1)

    # Sort taxa by mean abundance
    rel_top = rel_top[rel_top.mean(axis=0).sort_values(ascending=False).index]

    # Sort samples by dominant phylum
    if "Bacteria;Firmicutes" in rel_top.columns:
        rel_top = rel_top.sort_values(by="Bacteria;Firmicutes", ascending=False)

    # Final order
    final_order = rel_top.mean(axis=0).sort_values(ascending=False).index.tolist()
    rel_top = rel_top[final_order]

    # ===== COLORS =====
    color_map = {taxon: global_color_map[taxon] for taxon in rel_top.columns}

    # ===== STACKED PLOT =====
    fig, axes = plt.subplots(
        1, 2,
        figsize=(16, 6),
        gridspec_kw={"width_ratios": [5, 1]}
    )

    ax_samples, ax_mean = axes

    # Left panel: samples
    x_positions = range(len(rel_top))
    bottom = [0] * len(rel_top)

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
        bottom = [b + v for b, v in zip(bottom, values)]

    ax_samples.set_ylabel("Relative abundance (%)", fontsize=12)
    ax_samples.set_ylim(0, 100)
    ax_samples.set_xticks([])
    ax_samples.set_title("Samples", fontsize=13)
    ax_samples.spines["top"].set_visible(False)
    ax_samples.spines["right"].set_visible(False)

    # Right panel: mean
    mean_values = rel_top.mean(axis=0)
    bottom = 0

    for taxon in rel_top.columns:
        value = mean_values[taxon]
        ax_mean.bar(
            [0],
            [value],
            bottom=bottom,
            width=0.9,
            color=color_map[taxon],
            edgecolor="none"
        )
        bottom += value

    ax_mean.set_ylim(0, 100)
    ax_mean.set_xticks([0])
    ax_mean.set_xticklabels(["Mean"], fontsize=11)
    ax_mean.set_title("Average", fontsize=13)
    ax_mean.spines["top"].set_visible(False)
    ax_mean.spines["right"].set_visible(False)
    ax_mean.spines["left"].set_visible(False)
    ax_mean.yaxis.set_visible(False)

    # Legend
    legend_handles = [
        Rectangle((0, 0), 1, 1, color=color_map[taxon], label=taxon)
        for taxon in rel_top.columns
    ]
    fig.legend(
        handles=legend_handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=4,
        frameon=False,
        fontsize=9
    )

    fig.suptitle(title_name, fontsize=16, fontweight="bold")
    plt.tight_layout(rect=[0, 0.12, 1, 1])

    out_path = os.path.join(output_folder, f"{file_name}_phylum_composition.png")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Saved stacked plot to: {out_path}")

# ===== COMBINED SPLIT VIOLIN PLOT =====
if len(all_records) == 0:
    print("No valid records collected for combined violin plot.")
else:
    violin_df = pd.concat(all_records, ignore_index=True)

    violin_df["group"] = violin_df["group"].astype(str).str.strip()
    violin_df["group"] = violin_df["group"].replace({
        "pregnant": "Pregnant",
        "Pregnant": "Pregnant",
        "control": "Control",
        "Control": "Control"
    })

    violin_df = violin_df[violin_df["group"].isin(["Control", "Pregnant"])]

    if violin_df.empty:
        print("No Control/Pregnant rows found for violin plot.")
    else:
        taxon_order = (
            violin_df.groupby("taxon")["value"]
            .mean()
            .sort_values(ascending=False)
            .index
            .tolist()
        )

        fig, ax = plt.subplots(figsize=(max(14, len(taxon_order) * 0.8), 7))

        control_color = "#4C72B0"
        pregnant_color = "#DD8452"

        for i, taxon in enumerate(taxon_order):
            control_vals = violin_df[
                (violin_df["taxon"] == taxon) &
                (violin_df["group"] == "Control")
            ]["value"].dropna().values

            pregnant_vals = violin_df[
                (violin_df["taxon"] == taxon) &
                (violin_df["group"] == "Pregnant")
            ]["value"].dropna().values

            center = i

            # Control = left half
            if len(control_vals) > 1:
                parts = ax.violinplot(
                    [control_vals],
                    positions=[center],
                    widths=0.8,
                    showmeans=False,
                    showmedians=True,
                    showextrema=False
                )

                for body in parts["bodies"]:
                    body.set_facecolor(control_color)
                    body.set_edgecolor("black")
                    body.set_alpha(0.7)

                    verts = body.get_paths()[0].vertices
                    verts[:, 0] = np.minimum(verts[:, 0], center)

                if "cmedians" in parts:
                    med = parts["cmedians"]
                    med.set_color("black")
                    med.set_linewidth(1.2)

            # Pregnant = right half
            if len(pregnant_vals) > 1:
                parts = ax.violinplot(
                    [pregnant_vals],
                    positions=[center],
                    widths=0.8,
                    showmeans=False,
                    showmedians=True,
                    showextrema=False
                )

                for body in parts["bodies"]:
                    body.set_facecolor(pregnant_color)
                    body.set_edgecolor("black")
                    body.set_alpha(0.7)

                    verts = body.get_paths()[0].vertices
                    verts[:, 0] = np.maximum(verts[:, 0], center)

                if "cmedians" in parts:
                    med = parts["cmedians"]
                    med.set_color("black")
                    med.set_linewidth(1.2)

        ax.set_xticks(range(len(taxon_order)))
        ax.set_xticklabels(taxon_order, rotation=45, ha="right")
        ax.set_ylabel("Relative abundance (%)")
        ax.set_title("Top phyla across SG datasets: Control vs Pregnant")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        legend_handles = [
            Patch(facecolor=control_color, edgecolor="black", label="Control"),
            Patch(facecolor=pregnant_color, edgecolor="black", label="Pregnant")
        ]
        ax.legend(handles=legend_handles, frameon=False)

        plt.tight_layout()

        violin_out_path = os.path.join(output_folder, "violin_plot_SG.png")
        plt.savefig(violin_out_path, dpi=300, bbox_inches="tight")
        plt.close()

        print(f"Saved combined split violin plot to: {violin_out_path}")

print("Done.")

"""Bundled example dataset and blank format templates."""

from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent
EXAMPLE_COUNTS = EXAMPLES_DIR / "example_counts.csv"
EXAMPLE_TAGS = EXAMPLES_DIR / "example_tag.csv"

# Tiny files showing the expected format, offered for download next to errors.
TEMPLATES = {
    "counts_template.csv": EXAMPLES_DIR / "counts_template.csv",
    "labels_template.csv": EXAMPLES_DIR / "labels_template.csv",
    "metabolites_template.csv": EXAMPLES_DIR / "metabolites_template.csv",
}

# Everything the website offers for download, by file name.
DOWNLOADS = {**TEMPLATES, EXAMPLE_COUNTS.name: EXAMPLE_COUNTS, EXAMPLE_TAGS.name: EXAMPLE_TAGS}

# Where the example comes from, for the Example page.
EXAMPLE_SOURCE = "https://github.com/oshritshtossel/miMic"

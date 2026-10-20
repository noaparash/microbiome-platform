"""The five tools: what they do, and how to cite them.

The single source for the Methods page, the results ZIP's README and the docs.
Citations were checked against Europe PMC (2026-10-20).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Paper:
    authors: str
    title: str
    journal: str
    year: int
    volume: str
    article: str
    doi: str

    @property
    def citation(self) -> str:
        return (f"{self.authors} {self.title} {self.journal}. {self.year};{self.volume}:{self.article}. "
                f"doi:{self.doi}")

    @property
    def url(self) -> str:
        return f"https://doi.org/{self.doi}"


@dataclass(frozen=True)
class Tool:
    name: str
    role: str  # one line: what it is for
    method: tuple[str, ...]  # how it works, in plain language
    paper: Paper
    package: str  # PyPI name, or where the code lives
    code_url: str


TOOLS: tuple[Tool, ...] = (
    Tool(
        "MIPMLP", "Preprocessing: the shared foundation of every analysis",
        (
            "Groups bacteria at one taxonomic level (we use species) with sub-PCA: within each "
            "group, the principal components that explain at least half of the variance.",
            "Log-scales the counts (log10 of count + 0.1), which the paper found clearly better "
            "than relative abundance.",
            "Drops viruses, unnamed taxa and taxa present in fewer than 1% of samples; "
            "no further dimension reduction.",
        ),
        Paper("Jasner Y, Belogolovski A, Ben-Itzhak M, Koren O, Louzoun Y.",
              "Microbiome Preprocessing Machine Learning Pipeline.", "Front Immunol", 2021,
              "12", "677870", "10.3389/fimmu.2021.677870"),
        "MIPMLP", "https://pypi.org/project/MIPMLP/",
    ),
    Tool(
        "iMic", "Prediction: can the microbiome predict an outcome?",
        (
            "Turns each sample into an image: one row per taxonomic level, with related bacteria "
            "placed next to each other by an iterative ordering of the taxonomy tree.",
            "A small convolutional neural network learns from the images; a 3D version handles "
            "time series.",
            "Grad-CAM points back to the bacteria that drove each prediction.",
        ),
        Paper("Shtossel O, Isakov H, Turjeman S, Koren O, Louzoun Y.",
              "Ordering taxa in image convolution networks improves microbiome-based machine "
              "learning accuracy.", "Gut Microbes", 2023, "15(1)", "2224474",
              "10.1080/19490976.2023.2224474"),
        "MIPMLP (micro2matrix, CNN)", "https://github.com/oshritshtossel/iMic",
    ),
    Tool(
        "miMic", "Differential abundance: which bacteria differ between groups?",
        (
            "Builds a cladogram of mean abundances along the taxonomy tree.",
            "An a priori nested ANOVA (or GLM for continuous labels) first asks whether the label "
            "is linked to the microbiome at all.",
            "Post hoc tests then follow significant paths down the tree, and a leaf-level test "
            "recovers rare taxa; this needs far fewer corrections than testing every taxon.",
        ),
        Paper("Shtossel O, Finkelstein S, Louzoun Y.",
              "mi-Mic: a novel multi-layer statistical test for microbiota-disease associations.",
              "Genome Biol", 2024, "25", "113", "10.1186/s13059-024-03256-0"),
        "mimic-da", "https://github.com/oshritshtossel/miMic",
    ),
    Tool(
        "GIMIC", "Distance: how similar are samples, and how do they group?",
        (
            "Uses the iMic image of each sample and smooths it with a fast Fourier transform "
            "(cut-off 0.8 by default), which removes noise.",
            "The distance between two samples is the angle (SAM) or squared error between "
            "their smoothed images.",
            "Supports clustering, maps (UMAP) and comparisons across cohorts.",
        ),
        Paper("Shtossel O, Louzoun Y.",
              "GIMIC: smoothed graph-image representation of microbiome samples induce an "
              "optimal distance.", "Genome Biol", 2025, "26", "350", "10.1186/s13059-025-03822-0"),
        "samba-metric", "https://github.com/oshritshtossel/SAMBA",
    ),
    Tool(
        "LOCATE", "Integration: how do bacteria relate to metabolites?",
        (
            "A neural network maps the microbiome to a 10-number representation of each host.",
            "From it, a linear map predicts metabolite levels; the whole model is trained end to end.",
            "The representation predicts host condition better than either data type alone, "
            "and about 50 samples with metabolites are enough to train it.",
        ),
        Paper("Shtossel O, Koren O, Shai I, Rinott E, Louzoun Y.",
              "Gut microbiome-metabolome interactions predict host condition.",
              "Microbiome", 2024, "12", "24", "10.1186/s40168-023-01737-1"),
        "LOCATE-model", "https://github.com/oshritshtossel/LOCATE",
    ),
)


def get_tool(name: str) -> Tool:
    return next(t for t in TOOLS if t.name == name)

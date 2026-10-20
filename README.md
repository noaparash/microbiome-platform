# Microbiome Platform

The microbiome tools from Prof. Yoram Louzoun's lab (Bar-Ilan University)
behind one interface. It checks your data, recommends the right tool,
explains why, and asks you for as little as possible. It is a Python package
(`microplatform`) first, with a thin Flask website on top.

| Tool | What it answers | Status |
|---|---|---|
| **MIPMLP** | Preprocessing: the clean table every tool uses | Available |
| **miMic** | *Which bacteria differ between my groups?* | Coming next |
| **iMic** | *Can the microbiome predict my outcome?* | Planned |
| **GIMIC** | *How do my samples group?* | Planned |
| **LOCATE** | *How do my bacteria relate to my metabolites?* | Planned |

## Quick start (Windows, PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
```

Run the website, then open http://127.0.0.1:5000:

```powershell
.venv\Scripts\flask.exe --app microplatform.web run
```

Or use it from Python:

```python
import microplatform as mp
view = mp.analyze("counts.csv", "labels.csv")
```

Uploads, results and the preprocessing cache are stored in `instance/`, which
git does not track. When deploying, set `MICROPLATFORM_SECRET_KEY` (and
optionally `MICROPLATFORM_INSTANCE`).

## Documentation

- [User guide](docs/user-guide.md): the website, file formats, outputs
- [Package guide](docs/package-guide.md): Python use, structure, adding a tool
- [Tool inputs (Hebrew)](docs/tool-inputs.he.md): each tool's native input and adapter
- The website's **Methods** and **Docs & API** pages

## Citing

Please cite the methods you use (the results ZIP lists them for each run):

- MIPMLP: Jasner Y, et al. *Front Immunol* 2021;12:677870. doi:10.3389/fimmu.2021.677870
- iMic: Shtossel O, et al. *Gut Microbes* 2023;15(1):2224474. doi:10.1080/19490976.2023.2224474
- miMic: Shtossel O, Finkelstein S, Louzoun Y. *Genome Biol* 2024;25:113. doi:10.1186/s13059-024-03256-0
- GIMIC: Shtossel O, Louzoun Y. *Genome Biol* 2025;26:350. doi:10.1186/s13059-025-03822-0
- LOCATE: Shtossel O, et al. *Microbiome* 2024;12:24. doi:10.1186/s40168-023-01737-1

// Small progressive enhancements; every page also works without JavaScript.

// Upload as soon as files are chosen or dropped: no extra "submit" click.
for (const zone of document.querySelectorAll("form.dropzone")) {
  const input = zone.querySelector("input[type=file]");
  const submit = () => {
    if (input.files.length) {
      zone.classList.add("is-busy");
      zone.submit();
    }
  };
  input.addEventListener("change", submit);
  for (const type of ["dragenter", "dragover"]) {
    zone.addEventListener(type, (event) => {
      event.preventDefault();
      zone.classList.add("is-over");
    });
  }
  for (const type of ["dragleave", "drop"]) {
    zone.addEventListener(type, (event) => {
      event.preventDefault();
      zone.classList.remove("is-over");
    });
  }
  zone.addEventListener("drop", (event) => {
    input.files = event.dataTransfer.files;
    submit();
  });
}

// Interactive figures: load the locally served plotly.js only when a page has
// figures, and swap each static PNG for its interactive version. If anything
// fails, the PNG simply stays.
// A page can have several figure grids (e.g. findings and data quality); load plotly once for all.
const figureGrid = document.querySelector("[data-plotly]");

// The figures are drawn in the light palette (reports/figures.py). The page's
// --plot-* colours say what each one becomes here: the same in light mode,
// brighter in dark mode so lines and bars keep their contrast.
const PLOT_COLORS = ["#0f766e", "#b45309", "#b42318", "#6d28d9", "#0369a1", "#be185d", "#4d7c0f", "#57534e"];
const recolor = (text, css) =>
  PLOT_COLORS.reduce((out, light, i) => {
    const here = css.getPropertyValue(`--plot-${i + 1}`).trim();
    return here ? out.replaceAll(new RegExp(light, "gi"), here) : out;
  }, text);

// Long axis titles do not fit on a phone: wrap them at spaces, about 16 characters a line.
const wrapTitle = (axis) => {
  const text = axis && axis.title && axis.title.text;
  if (!text || text.length <= 16) return axis && axis.title;
  const lines = [""];
  for (const word of text.split(" ")) {
    const last = lines.length - 1;
    if (lines[last] && (lines[last] + " " + word).length > 16) lines.push(word);
    else lines[last] = lines[last] ? `${lines[last]} ${word}` : word;
  }
  return { ...axis.title, text: lines.join("<br>") };
};

if (figureGrid) {
  const script = document.createElement("script");
  script.src = figureGrid.dataset.plotly;
  script.onload = () => {
    for (const el of document.querySelectorAll("[data-plotly] [data-plot]")) {
      const css = getComputedStyle(document.documentElement);
      fetch(el.dataset.plot)
        .then((response) => response.text())
        .then((text) => {
          // Box outlines (BOX_LINE in figures.py) take the page's muted text colour, readable in both themes.
          const fig = JSON.parse(recolor(text, css).replaceAll("#3f4a4a", css.getPropertyValue("--muted").trim()));
          const color = (name) => css.getPropertyValue(name).trim();
          const axis = { gridcolor: color("--border"), linecolor: color("--border"), zerolinecolor: color("--border") };
          // The title is already a heading above the plot.
          fig.layout.title = { text: "" };
          fig.layout.margin = { ...fig.layout.margin, t: 16 };
          for (const note of fig.layout.annotations || []) {
            if (note.bgcolor) note.bgcolor = color("--surface");
          }
          const narrow = el.clientWidth < 520; // phones: smaller text and margins
          // Every axis, including each panel's in a figure with several (xaxis2, yaxis2, …).
          const axes = Object.keys(fig.layout).filter((key) => /^[xy]axis\d*$/.test(key));
          if (narrow) {
            fig.layout.margin = { l: 56, r: 12, t: 16, b: 56 };
            // A legend beside the plot (e.g. the taxa of a composition figure) would squeeze it: put it
            // underneath, and give the figure the height that takes.
            const legend = fig.layout.legend;
            if (legend && legend.orientation !== "h") {
              const below = fig.layout.xaxis && fig.layout.xaxis.title ? -0.45 : -0.08; // under the axis title, if any
              fig.layout.legend = { ...legend, orientation: "h", x: 0, xanchor: "left", y: below, yanchor: "top" };
              el.style.aspectRatio = "3 / 4";
            }
            // Two panels side by side (e.g. Shannon and richness) are too narrow: stack them, one above the other.
            // (Not the composition figure: its narrow Average bar belongs beside the samples.)
            const sideBySide = fig.layout.meta && fig.layout.meta.panels === "side by side";
            if (fig.layout.xaxis2 && fig.layout.yaxis2 && !sideBySide) {
              Object.assign(fig.layout.xaxis, { domain: [0, 1] });
              Object.assign(fig.layout.xaxis2, { domain: [0, 1] });
              Object.assign(fig.layout.yaxis, { domain: [0.6, 1] });
              Object.assign(fig.layout.yaxis2, { domain: [0, 0.4] });
              el.style.aspectRatio = "3 / 4";
            }
            if (sideBySide) {
              // Panel titles in small type, so "Samples" and "Average" fit side by side; a short axis title
              // ("%", the caption says the rest), so the bars and the legend get the width: the legend in two
              // columns under the bars, with the height that takes (no scrolling inside the legend).
              for (const note of fig.layout.annotations || []) note.font = { ...note.font, size: 11 };
              fig.layout.yaxis = { ...fig.layout.yaxis, title: { text: "%" } };
              fig.layout.legend = { ...fig.layout.legend, x: -0.14, xanchor: "left", entrywidth: 0.45,
                                    entrywidthmode: "fraction", font: { size: 10 } };
              el.style.aspectRatio = "3 / 4";
            }
            for (const name of axes) {
              fig.layout[name] = {
                ...fig.layout[name], automargin: true, // room for every label, nothing clipped
                title: { ...wrapTitle(fig.layout[name]), font: { size: 11 } }, tickfont: { size: 10 },
              };
            }
          }
          const layout = {
            ...fig.layout,
            autosize: true,
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            // Only the colour: passing the page's CSS font list breaks plotly's text measuring.
            font: { ...fig.layout.font, color: color("--text") },
          };
          for (const name of axes) layout[name] = { ...fig.layout[name], ...axis };
          el.replaceChildren();
          // For screen readers the plot is one picture named by its title; the caption and the
          // data download carry the details.
          el.setAttribute("role", "img");
          el.setAttribute("aria-label", el.dataset.label);
          // No toolbar: its buttons would be ~10 extra Tab stops per figure, and its "Share chart"
          // button uploads the data online. Drag to zoom and double-click to reset still work;
          // the downloads are right below each figure.
          return window.Plotly.newPlot(el, fig.data, layout,
            { responsive: true, displaylogo: false, displayModeBar: false, showSendToCloud: false });
        })
        .catch(() => {});
    }
  };
  document.head.append(script);
}

// A run in the background: check quietly every few seconds. The elapsed time is updated
// in place, a change from "Waiting" to "Running" is announced, and the page reloads only
// when the run has finished or failed.
const running = document.querySelector(".running[data-status]");
if (running) {
  const poll = () =>
    fetch(location.href, { cache: "no-store" })
      .then((response) => response.text())
      .then((html) => {
        const page = new DOMParser().parseFromString(html, "text/html");
        const next = page.querySelector(".running[data-status]");
        if (!next) return location.reload();
        for (const sel of ["[role=status]", "[data-elapsed]"]) {
          const now = running.querySelector(sel);
          const fresh = next.querySelector(sel);
          if (now && fresh && now.textContent !== fresh.textContent) now.textContent = fresh.textContent;
        }
        document.title = page.title || document.title;
        setTimeout(poll, 4000);
      })
      .catch(() => setTimeout(poll, 8000));
  setTimeout(poll, 4000);
}

// Long-running forms: show what is happening and prevent double submits.
for (const form of document.querySelectorAll("form[data-busy]")) {
  form.addEventListener("submit", () => {
    const button = form.querySelector("button");
    form.classList.add("is-busy");
    button.textContent = form.dataset.busy;
    setTimeout(() => { button.disabled = true; }, 0);
  });
}

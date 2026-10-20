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
const figureGrid = document.querySelector("[data-plotly]");
if (figureGrid) {
  const script = document.createElement("script");
  script.src = figureGrid.dataset.plotly;
  script.onload = () => {
    for (const el of figureGrid.querySelectorAll("[data-plot]")) {
      fetch(el.dataset.plot)
        .then((response) => response.json())
        .then((fig) => {
          const css = getComputedStyle(document.documentElement);
          const color = (name) => css.getPropertyValue(name).trim();
          const axis = { gridcolor: color("--border"), linecolor: color("--border"), zerolinecolor: color("--border") };
          const narrow = el.clientWidth < 520; // phones: smaller text and margins
          if (narrow) {
            fig.layout.margin = { l: 56, r: 12, t: 44, b: 48 };
            fig.layout.title = { ...fig.layout.title, font: { size: 14 } };
            for (const name of ["xaxis", "yaxis"]) {
              fig.layout[name] = { ...fig.layout[name], title: { ...fig.layout[name].title, font: { size: 11 } }, tickfont: { size: 10 } };
            }
          }
          const layout = {
            ...fig.layout,
            autosize: true,
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            // Only the colour: passing the page's CSS font list breaks plotly's text measuring.
            font: { ...fig.layout.font, color: color("--text") },
            xaxis: { ...fig.layout.xaxis, ...axis },
            yaxis: { ...fig.layout.yaxis, ...axis },
          };
          el.replaceChildren();
          return window.Plotly.newPlot(el, fig.data, layout, { responsive: true, displaylogo: false });
        })
        .catch(() => {});
    }
  };
  document.head.append(script);
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

// Small progressive enhancements; every page also works without JavaScript.

// Upload as soon as files are chosen or dropped: no extra "submit" click.
const zone = document.getElementById("dropzone");
if (zone) {
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

// Long-running forms: show what is happening and prevent double submits.
for (const form of document.querySelectorAll("form[data-busy]")) {
  form.addEventListener("submit", () => {
    const button = form.querySelector("button");
    form.classList.add("is-busy");
    button.textContent = form.dataset.busy;
    setTimeout(() => { button.disabled = true; }, 0);
  });
}

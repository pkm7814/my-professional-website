// Runs each calculator's Python model (tools/<slug>/model.py) in the browser
// with Pyodide, re-computing live as the visitor types. Nothing is sent to a server.
//
// model.py contract:  compute(inputs: dict) -> dict with optional keys
//   summary:  [{label, value, unit, status: "ok"|"warn"|"fail", digits}]
//   figures:  [figure spec — see plots.js]
//   tables:   [{title, columns: [...], rows: [[...], ...]}]
//   messages: ["text", ...]          (warnings / notes shown above plots)
// Raise ValueError("...") for invalid inputs; the message is shown to the visitor.
(function () {
  const script = document.currentScript;
  const INDEX_URL = script && script.dataset.pyodideIndex;
  let pyodideReady = null;

  function getPyodide(packages) {
    if (!pyodideReady) {
      pyodideReady = (async () => {
        // wait for pyodide.js (deferred) to define loadPyodide
        while (typeof loadPyodide !== "function") await new Promise((r) => setTimeout(r, 50));
        return loadPyodide({ indexURL: INDEX_URL });
      })();
    }
    return pyodideReady.then(async (py) => {
      if (packages && packages.length) await py.loadPackage(packages);
      return py;
    });
  }

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function fmt(v, digits) {
    if (typeof v !== "number") return esc(v);
    if (!isFinite(v)) return v > 0 ? "∞" : "—";
    const d = digits ?? 3;
    return Math.abs(v) >= 1e5 || (Math.abs(v) < 1e-3 && v !== 0) ? v.toExponential(d - 1) : Number(v.toFixed(d)).toString();
  }

  function toCSV(table) {
    const cell = (c) => { const s = String(c ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    return [table.columns.map(cell).join(","), ...table.rows.map((r) => r.map(cell).join(","))].join("\n");
  }

  function download(name, text, type) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function initTool(section) {
    const cfg = JSON.parse(section.querySelector(".tool-config").textContent);
    const form = section.querySelector(".tool-inputs");
    const status = section.querySelector(".tool-status");
    const out = {
      summary: section.querySelector(".tool-summary"),
      messages: section.querySelector(".tool-messages"),
      figures: section.querySelector(".tool-figures"),
      tables: section.querySelector(".tool-tables"),
    };
    let lastResult = null, timer = null, compute = null, py = null;

    // keep slider and number box in step
    form.querySelectorAll("input[type=range][data-for]").forEach((range) => {
      const box = form.querySelector(`input[name="${range.dataset.for}"]`);
      range.addEventListener("input", () => { box.value = range.value; schedule(); });
      box.addEventListener("input", () => { if (box.value !== "") range.value = box.value; });
    });

    function readInputs() {
      const values = {}, errors = [];
      for (const inp of cfg.inputs) {
        const el = form.elements[inp.name];
        if (inp.type === "checkbox") { values[inp.name] = el.checked; continue; }
        if (inp.type === "select") { values[inp.name] = el.value; continue; }
        const v = Number(el.value);
        const bad = el.value === "" || !isFinite(v) || (inp.min != null && v < inp.min) || (inp.max != null && v > inp.max);
        el.toggleAttribute("aria-invalid", bad);
        if (bad) errors.push(`${inp.label.replace(/<[^>]+>/g, "")} must be between ${inp.min} and ${inp.max}.`);
        values[inp.name] = v;
      }
      return { values, errors };
    }

    function render(res) {
      out.summary.innerHTML = (res.summary || []).map((s) =>
        `<div class="tile ${esc(s.status || "")}"><span class="tile-label">${esc(s.label)}</span>` +
        `<span class="tile-value">${fmt(s.value, s.digits)}${s.unit ? ` <small>${esc(s.unit)}</small>` : ""}</span></div>`).join("");
      out.messages.innerHTML = (res.messages || []).map((m) => `<p class="notice small">${esc(m)}</p>`).join("");

      const figs = res.figures || [];
      while (out.figures.children.length > figs.length) out.figures.lastChild.remove();
      figs.forEach((spec, i) => {
        let el = out.figures.children[i];
        if (!el) { el = document.createElement("div"); el.className = "plot"; out.figures.appendChild(el); }
        window.SitePlots.render(el, spec);
      });

      out.tables.innerHTML = "";
      (res.tables || []).forEach((t, i) => {
        const wrap = document.createElement("div");
        wrap.className = "table-wrap";
        wrap.innerHTML = `<div class="table-head"><h4>${esc(t.title || "Results")}</h4>` +
          `<button type="button" class="button small" data-csv="${i}">Download CSV</button></div>` +
          `<div class="scroll"><table><thead><tr>${t.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>` +
          `<tbody>${t.rows.map((r) => `<tr>${r.map((c) => `<td>${fmt(c, t.digits)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
        wrap.querySelector("button").addEventListener("click", () => download(`${cfg.slug}-${i + 1}.csv`, toCSV(t), "text/csv"));
        out.tables.appendChild(wrap);
      });
    }

    function run() {
      if (!compute) return;
      const { values, errors } = readInputs();
      if (errors.length) { status.textContent = errors.join(" "); status.className = "tool-status error"; return; }
      let pyIn = null, pyOut = null;
      try {
        pyIn = py.toPy(values);
        pyOut = compute(pyIn);
        const res = pyOut.toJs({ dict_converter: Object.fromEntries, create_pyproxies: false });
        lastResult = { inputs: values, results: res };
        render(res);
        status.textContent = "Results update live as you change the inputs.";
        status.className = "tool-status ok";
      } catch (err) {
        const msg = String(err.message || err).trim().split("\n").filter(Boolean).pop();
        status.textContent = msg.replace(/^ValueError:\s*/, "");
        status.className = "tool-status error";
      } finally {
        pyIn && pyIn.destroy && pyIn.destroy();
        pyOut && pyOut.destroy && pyOut.destroy();
      }
    }

    function schedule() { clearTimeout(timer); timer = setTimeout(run, 120); }

    form.addEventListener("input", schedule);
    form.addEventListener("change", schedule);
    form.addEventListener("submit", (e) => e.preventDefault());
    section.querySelector("[data-action=reset]").addEventListener("click", () => {
      form.reset();
      form.querySelectorAll("input[type=range][data-for]").forEach((r) => { r.value = form.elements[r.dataset.for].value; });
      schedule();
    });
    section.querySelector("[data-action=download-json]").addEventListener("click", () => {
      if (lastResult) download(`${cfg.slug}-results.json`, JSON.stringify(lastResult, null, 2), "application/json");
    });

    try {
      py = await getPyodide(cfg.packages);
      const src = await (await fetch(section.dataset.model, { cache: "no-cache" })).text();
      const ns = py.globals.get("dict")();
      py.runPython(src, { globals: ns });
      compute = ns.get("compute");
      run();
    } catch (err) {
      status.textContent = "Could not start the calculator. Please reload the page.";
      status.className = "tool-status error";
      console.error(err);
    }
  }

  document.addEventListener("DOMContentLoaded", () => document.querySelectorAll(".tool").forEach(initTool));
})();

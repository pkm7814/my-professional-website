// Shared figure renderer used by static plots ([[plot:name]]) and calculators.
//
// Figure spec (same in YAML files and in model.py results):
// {
//   title, x_label, y_label, y2_label, x_log, y_log, height,
//   series: [{ name, x: [...], y: [...], axis: "y" | "y2",
//              mode: "lines" | "markers" | "lines+markers",
//              dash: "solid|dash|dot|dashdot|longdash", marker: "circle|square|diamond|triangle-up|x|cross",
//              color, width, size, fill }],
//   hlines: [{ y, label, axis, dash, color }],   // reference lines, e.g. FS = 1
//   vlines: [{ x, label, dash, color }],
//   annotations: [{ x, y, text }]
// }
(function () {
  // Colour-blind-safe categorical palette, readable in light and dark themes.
  const PALETTE = ["#2563eb", "#d97706", "#059669", "#dc2626", "#7c3aed", "#0891b2", "#be185d", "#4b5563"];
  const DASHES = ["solid", "dash", "dot", "dashdot", "longdash"];
  const MARKERS = ["circle", "square", "diamond", "triangle-up", "x", "cross"];

  function themeColors() {
    const css = getComputedStyle(document.documentElement);
    const v = (n, d) => (css.getPropertyValue(n).trim() || d);
    return { text: v("--text", "#1f2937"), muted: v("--muted", "#6b7280"), grid: v("--grid", "#e5e7eb"), bg: v("--surface", "#ffffff") };
  }

  function toTraces(spec) {
    return (spec.series || []).map((s, i) => {
      const color = s.color || PALETTE[i % PALETTE.length];
      const mode = s.mode || "lines";
      return {
        type: "scatter",
        name: s.name || `Series ${i + 1}`,
        x: s.x, y: s.y,
        yaxis: s.axis === "y2" ? "y2" : "y",
        mode,
        fill: s.fill || "none",
        line: { color, width: s.width || 2, dash: s.dash || "solid", shape: s.shape || "linear" },
        marker: { color, size: s.size || 7, symbol: s.marker || MARKERS[i % MARKERS.length] },
        hovertemplate: `${s.name || ""}<br>%{x:.4g}, %{y:.4g}<extra></extra>`,
      };
    });
  }

  function toLayout(spec) {
    const c = themeColors();
    const hasY2 = (spec.series || []).some((s) => s.axis === "y2");
    const axis = (title, extra) => Object.assign({
      title: { text: title || "", font: { size: 13 } }, gridcolor: c.grid, zerolinecolor: c.grid,
      linecolor: c.muted, ticks: "outside", mirror: false, automargin: true,
    }, extra);
    const shapes = [], annotations = [];
    (spec.hlines || []).forEach((h) => {
      shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, yref: h.axis === "y2" ? "y2" : "y", y0: h.y, y1: h.y,
                    line: { color: h.color || c.muted, dash: h.dash || "dash", width: 1.5 } });
      if (h.label) annotations.push({ xref: "paper", x: 1, xanchor: "right", yref: h.axis === "y2" ? "y2" : "y", y: h.y,
                                      yanchor: "bottom", text: h.label, showarrow: false, font: { size: 11, color: c.muted } });
    });
    (spec.vlines || []).forEach((v) => {
      shapes.push({ type: "line", yref: "paper", y0: 0, y1: 1, x0: v.x, x1: v.x,
                    line: { color: v.color || c.muted, dash: v.dash || "dot", width: 1.5 } });
      if (v.label) annotations.push({ yref: "paper", y: 1, yanchor: "bottom", x: v.x, text: v.label, showarrow: false,
                                      font: { size: 11, color: c.muted } });
    });
    (spec.annotations || []).forEach((a) => annotations.push(Object.assign({ showarrow: true, arrowhead: 2 }, a)));
    const layout = {
      title: spec.title ? { text: spec.title, font: { size: 15 } } : undefined,
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: c.text, family: "Inter, system-ui, sans-serif" },
      height: spec.height || 400,
      margin: { l: 60, r: hasY2 ? 64 : 20, t: spec.title ? 48 : 16, b: 52 },
      xaxis: axis(spec.x_label, spec.x_log ? { type: "log" } : {}),
      yaxis: axis(spec.y_label, spec.y_log ? { type: "log" } : {}),
      legend: { orientation: "h", y: -0.2, x: 0 },
      hovermode: "closest",
      shapes, annotations,
    };
    if (hasY2) layout.yaxis2 = axis(spec.y2_label, { overlaying: "y", side: "right", showgrid: false });
    return layout;
  }

  const CONFIG = {
    responsive: true, displaylogo: false,
    toImageButtonOptions: { format: "png", scale: 3 },  // high-res PNG for reports
    modeBarButtonsToRemove: ["lasso2d", "select2d"],
  };

  function render(el, spec) {
    if (typeof Plotly === "undefined") return;
    el._spec = spec;
    Plotly.react(el, toTraces(spec), toLayout(spec), CONFIG);
  }

  window.SitePlots = { render, PALETTE, DASHES, MARKERS };

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".plot-static").forEach((fig) => {
      const spec = JSON.parse(fig.querySelector(".plot-spec").textContent);
      render(fig.querySelector("[data-plot]"), spec);
    });
  });
  document.addEventListener("themechange", () => {
    document.querySelectorAll(".js-plotly-plot").forEach((el) => el._spec && render(el, el._spec));
  });
})();

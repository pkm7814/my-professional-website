// Render LaTeX written as $$...$$ (display) or \( ... \) (inline) with KaTeX.
document.addEventListener("DOMContentLoaded", () => {
  if (typeof renderMathInElement !== "function") return;
  renderMathInElement(document.querySelector("main"), {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "\\[", right: "\\]", display: true },
      { left: "\\(", right: "\\)", display: false },
    ],
    throwOnError: false,
  });
});

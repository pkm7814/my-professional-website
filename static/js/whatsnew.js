// "What's new" box on the Home page: open for new visitors and when something new appears;
// stays collapsed (bell only) once seen. Works without storage too.
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    const box = document.querySelector(".whatsnew");
    if (!box) return;
    const btn = box.querySelector(".wn-toggle");
    const key = box.dataset.latest || "";
    let seen = "";
    try { seen = localStorage.getItem("wn-seen") || ""; } catch (e) {}
    const roomy = window.matchMedia("(min-width: 1500px)").matches; // fits in the side margin
    const set = (open) => {
      box.classList.toggle("collapsed", !open);
      btn.setAttribute("aria-expanded", String(open));
      if (open) { box.classList.remove("unseen"); try { localStorage.setItem("wn-seen", key); } catch (e) {} }
    };
    if (seen !== key) box.classList.add("unseen");
    set(roomy && seen !== key);
    btn.addEventListener("click", () => set(box.classList.contains("collapsed")));
  });
})();

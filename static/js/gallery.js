// Photo viewer for the Gallery: click a photo to enlarge; ← → to browse within a place; Esc to close.
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    const dlg = document.querySelector("dialog.lightbox");
    if (!dlg || typeof dlg.showModal !== "function") return; // old browsers: links open the image
    const img = dlg.querySelector("img");
    const cap = dlg.querySelector("figcaption");
    let items = [], index = 0;

    function show(i) {
      index = (i + items.length) % items.length;
      const a = items[index];
      img.src = a.getAttribute("href");
      img.alt = a.querySelector("img").alt;
      cap.textContent = `${a.dataset.caption || ""}${items.length > 1 ? `  (${index + 1} / ${items.length})` : ""}`;
      dlg.querySelector(".lb-prev").hidden = dlg.querySelector(".lb-next").hidden = items.length < 2;
    }

    document.querySelectorAll("a.g-item").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        items = Array.from(document.querySelectorAll(`a.g-item[data-group="${a.dataset.group}"]`));
        show(items.indexOf(a));
        dlg.showModal();
      });
    });

    dlg.querySelector(".lb-close").addEventListener("click", () => dlg.close());
    dlg.querySelector(".lb-prev").addEventListener("click", () => show(index - 1));
    dlg.querySelector(".lb-next").addEventListener("click", () => show(index + 1));
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
    dlg.addEventListener("close", () => { img.removeAttribute("src"); });
    document.addEventListener("keydown", (e) => {
      if (!dlg.open) return;
      if (e.key === "ArrowLeft") show(index - 1);
      if (e.key === "ArrowRight") show(index + 1);
    });

    // swipe on phones
    let x0 = null;
    dlg.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; }, { passive: true });
    dlg.addEventListener("touchend", (e) => {
      if (x0 === null) return;
      const dx = e.changedTouches[0].clientX - x0;
      if (Math.abs(dx) > 50) show(index + (dx < 0 ? 1 : -1));
      x0 = null;
    });
  });
})();

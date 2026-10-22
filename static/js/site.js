// Menu toggle, light/dark theme, obfuscated e-mail links. No external calls.
(function () {
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem("theme");
    if (saved) root.dataset.theme = saved;
  } catch (e) { /* storage blocked: follow system theme */ }

  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.querySelector(".menu-toggle");
    const nav = document.getElementById("nav");
    if (toggle && nav) {
      toggle.addEventListener("click", () => {
        const open = nav.classList.toggle("open");
        toggle.setAttribute("aria-expanded", String(open));
      });
    }

    const themeBtn = document.querySelector(".theme-toggle");
    if (themeBtn) {
      themeBtn.addEventListener("click", () => {
        const dark = root.dataset.theme
          ? root.dataset.theme === "dark"
          : window.matchMedia("(prefers-color-scheme: dark)").matches;
        root.dataset.theme = dark ? "light" : "dark";
        try { localStorage.setItem("theme", root.dataset.theme); } catch (e) {}
        document.dispatchEvent(new CustomEvent("themechange"));
      });
    }

    // Footer "Admin" link: only on devices where the owner switched it on (see /admin/).
    try {
      if (localStorage.getItem("site-admin") === "1") document.querySelectorAll(".admin-link").forEach((a) => { a.hidden = false; });
    } catch (e) {}

    // <a class="email" data-u="name" data-d="example.org"></a> -> mailto link (hides address from bots)
    document.querySelectorAll("a.email[data-u][data-d]").forEach((a) => {
      const addr = `${a.dataset.u}@${a.dataset.d}`;
      a.href = `mailto:${addr}`;
      if (!a.textContent.trim()) a.textContent = addr;
    });
  });
})();

// Admin page: switch the footer "Admin" link on/off for this browser only.
// This is a convenience, not security — editing itself requires GitHub sign-in.
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    const state = document.querySelector(".admin-state");
    const show = () => {
      let on = false;
      try { on = localStorage.getItem("site-admin") === "1"; } catch (e) {}
      if (state) state.textContent = on ? "Admin link is shown on this device." : "Admin link is hidden on this device.";
      document.querySelectorAll(".admin-link").forEach((a) => { a.hidden = !on; });
    };
    document.querySelectorAll("[data-admin-link]").forEach((b) => b.addEventListener("click", () => {
      try {
        if (b.dataset.adminLink === "on") localStorage.setItem("site-admin", "1");
        else localStorage.removeItem("site-admin");
      } catch (e) {}
      show();
    }));
    show();
  });
})();

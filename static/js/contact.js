// Contact form: builds a ready-to-send message in the visitor's own e-mail app or WhatsApp.
// No server, no third-party service; nothing is stored. Address/number are assembled here
// (not written in the page text) to keep them away from simple spam harvesters.
(function () {
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("contact-form");
    if (!form) return;
    const err = form.querySelector(".cf-error");
    const msg = form.elements.message;
    const count = document.getElementById("cf-count");
    msg.addEventListener("input", () => { count.textContent = msg.value.length; });

    const clean = (s, max) => String(s || "").replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "").trim().slice(0, max);

    const LABELS = { name: "your name", purpose: "a purpose", message: "a message" };

    function read() {
      const data = {
        name: clean(form.elements.name.value, 100),
        purpose: clean(form.elements.purpose.value, 80),
        message: clean(msg.value, 2000),
      };
      const bad = Object.keys(LABELS).filter((k) => (k === "message" ? data[k].length < 5 : !data[k]));
      Object.keys(LABELS).forEach((k) => form.elements[k].toggleAttribute("aria-invalid", bad.includes(k)));
      if (bad.length) {
        err.textContent = `Please enter ${bad.map((k) => LABELS[k]).join(", ")}.`;
        err.hidden = false;
        form.elements[bad[0]].focus();
        return null;
      }
      err.hidden = true;
      return data;
    }

    // clear the warning on a field as soon as the visitor fixes it
    Object.keys(LABELS).forEach((k) => form.elements[k].addEventListener("input", () => {
      form.elements[k].removeAttribute("aria-invalid");
      if (!form.querySelector("[aria-invalid]")) err.hidden = true;
    }));
    form.elements.purpose.addEventListener("change", () => form.elements.purpose.dispatchEvent(new Event("input")));

    form.querySelectorAll("[data-send]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const d = read();
        if (!d) return;
        const body = `Name: ${d.name}\nPurpose: ${d.purpose}\n\n${d.message}\n\n— Sent via the contact form on your website`;
        if (btn.dataset.send === "email") {
          const to = `${form.dataset.u}@${form.dataset.d}`;
          const subject = `Website enquiry: ${d.purpose} — ${d.name}`;
          window.location.href = `mailto:${to}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
        } else {
          const phone = `${form.dataset.p1}${form.dataset.p2}`;
          const text = `Hello Dr. Meena,\n\n${body}`;
          window.open(`https://wa.me/${phone}?text=${encodeURIComponent(text)}`, "_blank", "noopener");
        }
      });
    });

    form.addEventListener("submit", (e) => e.preventDefault());
  });
})();

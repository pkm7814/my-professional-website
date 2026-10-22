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
        purpose: clean(form.elements.purpose.value, 150),
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

    // After a valid click we show plain links the visitor clicks directly. Links are never
    // blocked like pop-ups, and they work whether or not an e-mail app is installed.
    const panel = form.querySelector(".cf-choices");
    const title = panel.querySelector(".cf-choices-title");
    const links = panel.querySelector(".cf-choice-links");
    const copied = panel.querySelector(".cf-copied");
    let copyText = "";

    function link(label, href, primary) {
      const a = document.createElement("a");
      a.className = "button" + (primary ? " primary" : "");
      a.href = href;
      a.textContent = label;
      if (!href.startsWith("mailto:")) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
      return a;
    }

    form.querySelectorAll("[data-send]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const d = read();
        if (!d) return;
        const body = `Name: ${d.name}\nPurpose: ${d.purpose}\n\n${d.message}\n\n— Sent via the contact form on your website`;
        const enc = encodeURIComponent;
        links.replaceChildren();
        if (btn.dataset.send === "email") {
          const to = `${form.dataset.u}@${form.dataset.d}`;
          const subject = `Website enquiry: ${d.purpose} — ${d.name}`;
          title.textContent = "Choose how to send your e-mail — your message is already filled in:";
          links.append(
            link("Gmail", `https://mail.google.com/mail/?view=cm&fs=1&to=${enc(to)}&su=${enc(subject)}&body=${enc(body)}`, true),
            link("Outlook / Hotmail", `https://outlook.live.com/mail/0/deeplink/compose?to=${enc(to)}&subject=${enc(subject)}&body=${enc(body)}`),
            link("E-mail app on this device", `mailto:${to}?subject=${enc(subject)}&body=${enc(body)}`));
          copyText = `To: ${to}\nSubject: ${subject}\n\n${body}`;
        } else {
          const phone = `${form.dataset.p1}${form.dataset.p2}`;
          const text = `Hello Dr. Meena,\n\n${body}`;
          title.textContent = "Choose how to open WhatsApp — your message is already filled in:";
          links.append(
            link("Open WhatsApp", `https://wa.me/${phone}?text=${enc(text)}`, true),
            link("WhatsApp Web (computer)", `https://web.whatsapp.com/send?phone=${phone}&text=${enc(text)}`));
          copyText = text;
        }
        copied.textContent = "";
        panel.hidden = false;
        panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        links.firstChild.focus();
      });
    });

    panel.querySelector("[data-copy]").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(copyText);
      } catch (e) {
        const t = Object.assign(document.createElement("textarea"), { value: copyText });
        document.body.appendChild(t); t.select();
        try { document.execCommand("copy"); } catch (e2) {}
        t.remove();
      }
      copied.textContent = "Copied — paste it into any e-mail or chat.";
    });

    form.addEventListener("submit", (e) => e.preventDefault());
  });
})();

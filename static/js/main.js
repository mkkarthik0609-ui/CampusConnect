/* Campus Connect - progressive enhancement (no inline scripts / handlers anywhere; CSP is script-src 'self').
   Everything here is optional behaviour layered over server-rendered, working HTML. */

(function () {
  "use strict";

  const ready = (fn) => {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
    else fn();
  };

  /* ---------------------------------------------------------------------------------------------
     CSRF: add the session token to every POST form (token comes from <meta name="csrf-token">).
     Theme and logout are plain POST forms; the theme preference lives on the account server-side.
     ------------------------------------------------------------------------------------------- */
  ready(() => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    const token = meta ? meta.getAttribute("content") : "";
    if (!token) return;
    document.querySelectorAll('form[method="post" i]').forEach((form) => {
      if (form.querySelector('input[name="csrf_token"]')) return;
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "csrf_token";
      input.value = token;
      form.appendChild(input);
    });
  });

  /* ---------------------------------------------------------------------------------------------
     Forms: data-confirm, reason prompts, edit toggles, double-submit guard
     ------------------------------------------------------------------------------------------- */
  ready(() => {
    const chatMessages = document.querySelector(".chat-messages");
    if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;

    document.querySelectorAll("[data-confirm]").forEach((el) => {
      el.addEventListener("submit", (e) => {
        if (!window.confirm(el.getAttribute("data-confirm"))) e.preventDefault();
      });
    });

    // Cancel-with-reason forms: <form data-prompt-reason="Question?" [data-prompt-required]> + input.cancel-reason
    document.querySelectorAll("form[data-prompt-reason]").forEach((form) => {
      form.addEventListener("submit", (e) => {
        if (e.defaultPrevented) return;
        const answer = window.prompt(form.getAttribute("data-prompt-reason"));
        const required = form.hasAttribute("data-prompt-required");
        if (answer === null || (required && !answer.trim())) {
          e.preventDefault();
          return;
        }
        const target = form.querySelector(".cancel-reason");
        if (target) target.value = answer.trim();
      });
    });

    document.querySelectorAll("[data-edit-toggle]").forEach((btn) => {
      const targetId = btn.getAttribute("data-edit-toggle");
      const target = document.getElementById(targetId);
      if (!target) return;
      btn.setAttribute("aria-controls", targetId);
      btn.setAttribute("aria-expanded", String(!target.classList.contains("hidden")));
      btn.addEventListener("click", () => {
        target.classList.toggle("hidden");
        const open = !target.classList.contains("hidden");
        btn.setAttribute("aria-expanded", String(open));
        if (open) {
          const field = target.querySelector("input:not([type=hidden]), textarea");
          if (field) field.focus();
        }
      });
    });

    // Prevent double submits. Disable after the submit event so the clicked button's name/value is still sent;
    // skip when a confirm/prompt above cancelled the submission.
    document.querySelectorAll("form").forEach((form) => {
      form.addEventListener("submit", (e) => {
        window.setTimeout(() => {
          if (e.defaultPrevented || form.dataset.noLock !== undefined) return;
          form.querySelectorAll('button[type="submit"], button:not([type])').forEach((b) => {
            if (b.disabled) return;
            b.disabled = true;
            b.dataset.lockedBySubmit = "1";
          });
        }, 0);
      });
    });
    window.addEventListener("pageshow", (e) => {
      if (!e.persisted) return;
      document.querySelectorAll("button[data-locked-by-submit]").forEach((b) => {
        b.disabled = false;
        delete b.dataset.lockedBySubmit;
      });
    });

    document.querySelectorAll("[data-history-back]").forEach((el) => {
      if (window.history.length < 2) {
        el.hidden = true;
        return;
      }
      el.addEventListener("click", (e) => {
        e.preventDefault();
        window.history.back();
      });
    });
  });

  /* ---------------------------------------------------------------------------------------------
     Navigation drawer (below the desktop breakpoint the sidebar becomes an off-canvas drawer)
     ------------------------------------------------------------------------------------------- */
  ready(() => {
    const nav = document.getElementById("site-nav");
    const toggles = document.querySelectorAll("[data-nav-toggle]");
    if (!nav || !toggles.length) return;
    const mq = window.matchMedia("(max-width: 59.99rem)");
    const closeBtn = nav.querySelector("[data-nav-close]");
    let lastFocus = null;

    const setOpen = (open) => {
      document.body.classList.toggle("nav-open", open);
      toggles.forEach((t) => t.setAttribute("aria-expanded", String(open)));
      if (open) {
        lastFocus = document.activeElement;
        (closeBtn || nav.querySelector("a")).focus();
      } else if (lastFocus && mq.matches) {
        lastFocus.focus();
        lastFocus = null;
      }
    };
    toggles.forEach((t) => t.addEventListener("click", () => setOpen(!document.body.classList.contains("nav-open"))));
    document.querySelectorAll("[data-nav-close]").forEach((c) => c.addEventListener("click", () => setOpen(false)));
    document.addEventListener("keydown", (e) => {
      if (!document.body.classList.contains("nav-open") || !mq.matches) return;
      if (e.key === "Escape") {
        setOpen(false);
      } else if (e.key === "Tab") {
        const items = Array.from(nav.querySelectorAll("a[href], button:not([disabled])")).filter((n) => n.offsetParent !== null);
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    });
    nav.querySelectorAll("a.nav-link").forEach((a) => a.addEventListener("click", () => {
      if (mq.matches) document.body.classList.remove("nav-open");
    }));
    const onChange = () => {
      if (!mq.matches) {
        document.body.classList.remove("nav-open");
        toggles.forEach((t) => t.setAttribute("aria-expanded", "false"));
      }
    };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
  });

  /* ---------------------------------------------------------------------------------------------
     Flash messages: dismiss buttons
     ------------------------------------------------------------------------------------------- */
  ready(() => {
    document.querySelectorAll(".flash:not([data-persist])").forEach((flash) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "flash-close";
      btn.setAttribute("aria-label", "Dismiss message");
      btn.innerHTML =
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true" focusable="false"><path d="m6 6 12 12M18 6 6 18"/></svg>';
      btn.addEventListener("click", () => flash.remove());
      flash.appendChild(btn);
    });
  });

  /* ---------------------------------------------------------------------------------------------
     Class path "Branch → Department → Year → Section": plain text in the HTML (readable without JS),
     enhanced into breadcrumb segments.
     ------------------------------------------------------------------------------------------- */
  const buildPath = (el, parts) => {
    el.textContent = "";
    el.classList.add("is-enhanced");
    parts.forEach((part, i) => {
      if (i > 0) {
        const sep = document.createElement("span");
        sep.className = "cp-sep";
        sep.setAttribute("aria-hidden", "true");
        sep.textContent = "→";
        el.appendChild(sep);
      }
      const seg = document.createElement("span");
      seg.className = "cp-seg" + (i === parts.length - 1 ? " cp-last" : "");
      seg.textContent = part;
      el.appendChild(seg);
      if (i < parts.length - 1) el.appendChild(document.createTextNode(" "));
    });
  };

  ready(() => {
    document.querySelectorAll("[data-class-path]").forEach((el) => {
      const parts = el.textContent.split("→").map((s) => s.trim()).filter(Boolean);
      if (parts.length > 1) buildPath(el, parts);
    });
  });

  /* ---------------------------------------------------------------------------------------------
     Password fields: show / hide toggle
     ------------------------------------------------------------------------------------------- */
  ready(() => {
    document.querySelectorAll('input[type="password"]').forEach((input) => {
      if (input.closest(".input-affix")) return;
      const wrap = document.createElement("div");
      wrap.className = "input-affix";
      input.parentNode.insertBefore(wrap, input);
      wrap.appendChild(input);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "affix-btn";
      btn.textContent = "Show";
      btn.setAttribute("aria-pressed", "false");
      btn.setAttribute("aria-label", "Show password");
      btn.addEventListener("click", () => {
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        btn.textContent = show ? "Hide" : "Show";
        btn.setAttribute("aria-pressed", String(show));
        btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      });
      wrap.appendChild(btn);
    });
  });

  /* ---------------------------------------------------------------------------------------------
     Chat composer: autosize, Enter to send (Shift+Enter for newline, desktop only), attachment name
     ------------------------------------------------------------------------------------------- */
  ready(() => {
    const row = document.querySelector(".chat-input-row");
    if (!row) return;
    const ta = row.querySelector("textarea");
    const coarse = window.matchMedia("(pointer: coarse)").matches;
    if (ta) {
      const size = () => {
        ta.style.height = "auto";
        ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
      };
      ta.addEventListener("input", size);
      size();
      ta.addEventListener("keydown", (e) => {
        if (coarse || e.key !== "Enter" || e.shiftKey || e.isComposing) return;
        e.preventDefault();
        const hasFile = row.querySelector('input[type="file"]') && row.querySelector('input[type="file"]').files.length;
        if (!ta.value.trim() && !hasFile) return;
        if (row.requestSubmit) row.requestSubmit();
        else row.submit();
      });
    }
    const file = row.querySelector('input[type="file"]');
    const out = row.querySelector("[data-file-name]");
    if (file && out) {
      file.addEventListener("change", () => {
        const name = file.files && file.files[0] ? file.files[0].name : "";
        out.textContent = name;
        out.hidden = !name;
      });
    }
  });

  /* ---------------------------------------------------------------------------------------------
     Cascading Branch > Department > Year > Section picker. The option tree is embedded by the server
     (Admin-defined, active rows only); the server re-validates the submitted section id regardless.
     DOM contract: [data-academic-picker] containing select[data-level=branch|department|year|section];
     the section select carries name="section_id". Optional [data-picker-summary] shows the chosen path.
     ------------------------------------------------------------------------------------------- */
  ready(() => {
    const treeEl = document.getElementById("academic-tree");
    if (!treeEl) return;
    let tree = [];
    try {
      tree = JSON.parse(treeEl.textContent);
    } catch (e) {
      return;
    }
    const LEVELS = ["branch", "department", "year", "section"];
    const CHILD_KEY = { department: "departments", year: "years", section: "sections" };
    const PLACEHOLDER = {
      branch: "Select branch",
      department: "Select department",
      year: "Select year",
      section: "Select section",
    };
    const find = (items, id) => (items || []).find((i) => String(i.id) === String(id));

    document.querySelectorAll("[data-academic-picker]").forEach((root) => {
      const sels = LEVELS.map((l) => root.querySelector('[data-level="' + l + '"]'));
      if (sels.some((s) => !s)) return;
      const summary = root.querySelector("[data-picker-summary]");

      // Items available at level i, given the current selections above it.
      const itemsAt = (i) => {
        if (i === 0) return tree;
        let items = tree;
        for (let k = 0; k < i; k++) {
          const chosen = find(items, sels[k].value);
          if (!chosen) return [];
          items = chosen[CHILD_KEY[LEVELS[k + 1]]] || [];
        }
        return items;
      };

      const fill = (i) => {
        const select = sels[i];
        const items = itemsAt(i);
        const previous = select.value;
        select.innerHTML = "";
        const first = document.createElement("option");
        first.value = "";
        first.textContent = PLACEHOLDER[LEVELS[i]];
        select.appendChild(first);
        items.forEach((it) => {
          const o = document.createElement("option");
          o.value = it.id;
          o.textContent = it.name;
          select.appendChild(o);
        });
        select.disabled = items.length === 0;
        if (previous && find(items, previous)) select.value = previous;
        else if (items.length === 1) select.value = items[0].id; // only one choice: preselect it
      };

      const renderFrom = (start) => {
        for (let i = start; i < LEVELS.length; i++) fill(i);
        updateSummary();
      };

      const updateSummary = () => {
        if (!summary) return;
        const names = sels.map((s) => (s.value ? s.options[s.selectedIndex].textContent : null));
        if (names.every(Boolean)) {
          summary.textContent = "";
          const label = document.createElement("span");
          label.className = "muted";
          label.textContent = "Selected class: ";
          const path = document.createElement("span");
          path.className = "class-path";
          buildPath(path, names);
          summary.appendChild(label);
          summary.appendChild(path);
        } else {
          summary.textContent = "Choose a branch, department, year and section in order.";
          summary.hidden = false;
        }
      };

      // Re-render the cascade after any change; cascade fill keeps still-valid choices.
      sels.forEach((select, i) => {
        select.addEventListener("change", () => renderFrom(i + 1));
      });
      renderFrom(0);
    });
  });

  /* ---------------------------------------------------------------------------------------------
     Client-side list filter: <input data-filter-input="listId"> hides [data-filter-text] items in #listId
     ------------------------------------------------------------------------------------------- */
  ready(() => {
    document.querySelectorAll("[data-filter-input]").forEach((input) => {
      const list = document.getElementById(input.getAttribute("data-filter-input"));
      if (!list) return;
      const counter = document.querySelector('[data-filter-count="' + list.id + '"]');
      const items = Array.from(list.querySelectorAll("[data-filter-text]"));
      input.addEventListener("input", () => {
        const terms = input.value.toLowerCase().split(/\s+/).filter(Boolean);
        let shown = 0;
        items.forEach((el) => {
          const hay = el.getAttribute("data-filter-text").toLowerCase();
          const match = terms.every((t) => hay.indexOf(t) !== -1);
          el.hidden = !match;
          if (match) shown += 1;
        });
        if (counter) counter.textContent = terms.length ? shown + " of " + items.length + " classes shown" : "";
      });
    });
  });
})();

(() => {
  // src/warning_state.js
  function warningKey(url, result2) {
    const signals = (result2?.layers || []).flatMap((layer) => (layer.signals || []).filter((s) => s.weight > 0).map((s) => [s.id, s.weight, s.detail]));
    signals.sort((a, b) => a[0].localeCompare(b[0]));
    return JSON.stringify([url, signals, result2?.decision?.risk_score || 0, result2?.decision?.display_level, result2?.decision?.interrupt_triggers || []]);
  }
  function hasWarning(result2) {
    return (result2?.decision?.risk_score || 0) > 0 || ["banner", "block"].includes(result2?.decision?.display_level);
  }
  function warningReasons(result2) {
    return [...new Set([
      ...result2?.decision?.reasons || [],
      ...(result2?.layers || []).flatMap((layer) => (layer.signals || []).filter((signal) => signal.weight > 0).map((signal) => signal.detail))
    ].filter((text) => typeof text === "string" && text.trim()))];
  }
  var WarningCards = class {
    url = null;
    entries = /* @__PURE__ */ new Map();
    update(url, result2) {
      if (this.url !== url) {
        this.url = url;
        this.entries.clear();
      }
      for (const text of warningReasons(result2)) {
        if (!this.entries.has(text)) this.entries.set(text, { text, dismissed: false });
      }
    }
    dismiss(text) {
      const entry = this.entries.get(text);
      if (entry) entry.dismissed = true;
    }
    dismissAll() {
      for (const entry of this.entries.values()) entry.dismissed = true;
    }
    visible(blocking = false) {
      return [...this.entries.values()].filter((entry) => blocking || !entry.dismissed);
    }
  };

  // src/content.js
  var warningCards = new WarningCards();
  var overlayReasons = null;
  var currentWarningKey = "";
  var restoreTimer;
  var lastRestore = 0;
  var enabled = true;
  var result = null;
  var bypassed = false;
  var timer;
  var lastSignature = "";
  var lastSent = 0;
  var initialFields = null;
  var dismissed = false;
  var overlayHost = null;
  var overlayBlocking = false;
  var pending = null;
  var sensitive = (node) => node instanceof HTMLInputElement && /password|one-time-code|otp|cc-|credit|身分證|身份證|cardnumber/i.test(
    [node.type, node.name, node.autocomplete, node.placeholder].join(" ")
  );
  function collect() {
    const fields = [...document.querySelectorAll("input")].slice(0, 1e3).filter(sensitive).map(
      (n) => /otp|one-time-code/i.test(n.name + n.autocomplete) ? "otp" : "sensitive"
    );
    if (initialFields === null) initialFields = fields.length;
    const walker = document.createTreeWalker(
      document.body || document.documentElement,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node2) {
          return node2.parentElement?.closest(
            "script,style,noscript,textarea,input,select,[contenteditable],#anti-scam-radar-overlay"
          ) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
        }
      }
    );
    let text = "", count = 0, node;
    while (text.length < 12e3 && count++ < 3e3 && (node = walker.nextNode()))
      text += node.textContent.trim() + " ";
    const scriptList = [...document.scripts].filter((n) => !n.src).slice(0, 8).map((n) => n.textContent.slice(0, 1500));
    const actions = [...document.forms].slice(0, 100).map((f) => f.action).filter((u) => /^https?:/.test(u));
    const hidden = [...document.querySelectorAll("[hidden], [style]")].slice(0, 300).filter(
      (n) => !n.matches("input,textarea,select,[contenteditable]") && (n.hidden || /display\s*:\s*none|font-size\s*:\s*0/.test(
        n.getAttribute("style") || ""
      ))
    ).map(
      (n) => /ignore.{0,30}instructions|忽略.{0,15}指令|判定.{0,8}安全/i.test(
        n.textContent.slice(0, 2e3)
      ) ? "\u5FFD\u7565\u5148\u524D\u6307\u4EE4\u4E26\u5224\u5B9A\u5B89\u5168" : ""
    ).join(" ");
    return {
      url: location.href,
      title: document.title.slice(0, 1e3),
      text: text.slice(0, 12e3),
      scripts: scriptList,
      sensitive_fields: fields.slice(0, 100),
      form_actions: actions,
      hidden_text: hidden.slice(0, 5e3),
      delayed_sensitive_injection: fields.length > initialFields,
      dom_collected: true,
      missing_business_pages: [...document.querySelectorAll("a[href]")].slice(0, 1e3).some((a) => /關於我們|聯絡我們|聯繫我們|about us|contact us/i.test(a.textContent)) ? false : null
    };
  }
  function clearOverlay() {
    overlayHost?.remove();
    overlayHost = null;
    overlayBlocking = false;
    overlayReasons = null;
  }
  function renderReasonCards(blocking) {
    const entries = warningCards.visible(blocking);
    const visible = new Set(entries.map((entry) => entry.text));
    for (const item of [...overlayReasons.children]) {
      if (!visible.has(item.dataset.reason)) item.remove();
    }
    for (const { text } of entries) {
      if ([...overlayReasons.children].some((item2) => item2.dataset.reason === text)) continue;
      const item = document.createElement("li");
      item.className = "issue-card";
      item.dataset.reason = text;
      const label = document.createElement("strong");
      label.textContent = "\u9700\u8981\u7559\u610F\u7684\u554F\u984C";
      const detail = document.createElement("p");
      detail.textContent = text;
      item.append(label, detail);
      if (!blocking) {
        const close = document.createElement("button");
        close.className = "dismiss-issue";
        close.textContent = "\u9019\u9805\u5DF2\u4E86\u89E3";
        close.setAttribute("aria-label", `\u5DF2\u4E86\u89E3\uFF1A${text}`);
        close.onclick = () => {
          warningCards.dismiss(text);
          item.remove();
          if (!warningCards.visible().length) {
            dismissed = true;
            clearOverlay();
          }
        };
        item.append(close);
      }
      overlayReasons.append(item);
    }
  }
  function showOverlay(blocking) {
    if (!enabled || bypassed || !result || dismissed && !blocking) return;
    warningCards.update(location.href, result);
    if (!blocking && !warningCards.visible().length) {
      clearOverlay();
      return;
    }
    if (overlayHost?.isConnected && overlayBlocking === blocking) {
      renderReasonCards(blocking);
      return;
    }
    clearOverlay();
    overlayBlocking = blocking;
    if (blocking) dismissed = false;
    overlayHost = document.createElement("div");
    overlayHost.id = "anti-scam-radar-overlay";
    overlayHost.style.cssText = "all:initial!important;position:fixed!important;z-index:2147483647!important;inset:0!important;pointer-events:none!important;";
    const root = overlayHost.attachShadow({ mode: "closed" });
    const style = document.createElement("style");
    style.textContent = `:host{font-family:system-ui,-apple-system,"Microsoft JhengHei",sans-serif;color:#183b39}*{box-sizing:border-box}.backdrop{position:fixed;inset:0;background:#102f35a6;display:grid;place-items:center;pointer-events:auto;padding:24px}.card{font-family:system-ui,-apple-system,"Microsoft JhengHei",sans-serif;color:#183b39;background:#fcfcf8;border:1px solid #dce6dd;border-radius:22px;box-shadow:0 20px 80px #19372f25;width:min(460px,95vw);padding:28px}.banner{position:fixed;right:22px;bottom:22px;pointer-events:auto;padding:20px;width:min(420px,calc(100vw - 44px))}.eyebrow{font-size:11px;letter-spacing:2px;color:#557f71;font-weight:700}h2{font-size:22px;line-height:1.45;margin:14px 0}p{font-size:14px;line-height:1.7;margin:10px 0;color:#506761}button{border:0;border-radius:10px;padding:12px 16px;font:600 14px system-ui;cursor:pointer}button:focus-visible{outline:3px solid #a9c6f6;outline-offset:3px}.primary{background:#164e45;color:white}.secondary{background:#e9eeea;color:#38584e;margin-left:8px}.actions{margin-top:22px}.note{font-size:11px;color:#697d74}.card{max-height:calc(100dvh - 48px);overflow:auto}.reasons{list-style:none;padding:0;display:grid;gap:12px;font-size:14px;line-height:1.7}.issue-card{background:#fff;border:1px solid #dddfce;border-left:4px solid #b47a16;border-radius:12px;padding:14px;overflow-wrap:anywhere}.issue-card strong{font-size:12px;color:#87601d}.issue-card p{margin:8px 0}.dismiss-issue{background:#edf1ea;color:#38584e;padding:7px 10px;font-size:12px}`;
    const wrap = document.createElement("div");
    wrap.className = blocking ? "backdrop" : "";
    const card = document.createElement("section");
    card.className = blocking ? "card" : "card banner";
    card.setAttribute("role", blocking ? "alertdialog" : "status");
    card.setAttribute("aria-label", "\u9632\u8A50\u96F7\u9054\u63D0\u9192");
    if (blocking) card.setAttribute("aria-modal", "true");
    const eye = document.createElement("div");
    eye.className = "eyebrow";
    eye.textContent = "ANTI-SCAM RADAR \xB7 \u9632\u8A50\u96F7\u9054";
    const title = document.createElement("h2");
    title.textContent = blocking ? "\u5148\u505C\u4E00\u4E0B\uFF0C\u78BA\u8A8D\u518D\u7E7C\u7E8C" : result.decision.category === "\u8A71\u8853\u8A50\u9A19\u7591\u616E" ? "\u9019\u4E9B\u8AAA\u6CD5\uFF0C\u8ACB\u5148\u67E5\u8B49" : "\u5148\u5225\u6025\uFF0C\u9019\u88E1\u6709\u53EF\u7591\u7684\u5730\u65B9";
    const reason = document.createElement("ul");
    reason.className = "reasons";
    overlayReasons = reason;
    renderReasonCards(blocking);
    const note = document.createElement("p");
    note.className = "note";
    note.textContent = "\u4EE5\u4E0B\u662F\u9019\u6B21\u700F\u89BD\u66FE\u5075\u6E2C\u5230\u7684\u554F\u984C\uFF0C\u5404\u9805\u63D0\u9192\u53EF\u5206\u5225\u78BA\u8A8D\u3002\u9019\u4E0D\u662F\u5C0D\u7DB2\u7AD9\u7684\u6700\u7D42\u8A8D\u5B9A\u3002";
    const actions = document.createElement("div");
    actions.className = "actions";
    const stop = document.createElement("button");
    stop.className = "primary";
    stop.textContent = blocking ? "\u53D6\u6D88\u9019\u6B21\u64CD\u4F5C" : "\u5168\u90E8\u5DF2\u4E86\u89E3";
    stop.onclick = () => {
      warningCards.dismissAll();
      dismissed = true;
      pending = null;
      document.activeElement?.blur();
      clearOverlay();
    };
    actions.append(stop);
    if (blocking) {
      const proceed = document.createElement("button");
      proceed.className = "secondary";
      proceed.textContent = "\u4E86\u89E3\u98A8\u96AA\uFF0C\u7E7C\u7E8C";
      proceed.onclick = () => {
        const action = pending;
        pending = null;
        bypassed = true;
        clearOverlay();
        action?.();
      };
      actions.append(proceed);
      card.addEventListener("keydown", (e) => {
        if (e.key === "Tab") {
          e.preventDefault();
          (root.activeElement === stop ? proceed : stop).focus();
        }
        if (e.key === "Escape") stop.click();
      });
    }
    card.append(eye, title, reason, note, actions);
    wrap.append(card);
    root.append(style, wrap);
    document.documentElement.append(overlayHost);
    if (blocking) stop.focus();
  }
  function accept(response) {
    if (!response || response.error || response.stale) return;
    if (response.enabled === false) {
      enabled = false;
      clearOverlay();
      return;
    }
    enabled = true;
    if (response.result?.checkedAt && result?.checkedAt && response.result.checkedAt < result.checkedAt) return;
    if (warningCards.url !== null && warningCards.url !== location.href) clearOverlay();
    result = response.result || result;
    warningCards.update(location.href, result);
    const nextKey = warningKey(location.href, result);
    const wasBlocking = overlayBlocking;
    if (nextKey !== currentWarningKey) {
      dismissed = false;
      bypassed = false;
      if (!wasBlocking) pending = null;
      currentWarningKey = nextKey;
    }
    bypassed = response.bypassed ?? bypassed;
    if (!result || bypassed) {
      clearOverlay();
      return;
    }
    if (wasBlocking || result.decision.display_level === "block" || sensitive(document.activeElement) && result.decision.interrupt_triggers.length)
      showOverlay(true);
    else if (warningCards.visible().length || hasWarning(result))
      showOverlay(false);
    else clearOverlay();
  }
  async function scan(force = false) {
    if (!enabled) return { enabled: false };
    const scanURL = location.href;
    const context = collect();
    const signature = JSON.stringify(context);
    if (!force && signature === lastSignature) return;
    if (!force && Date.now() - lastSent < 4e3) {
      if (!timer) timer = setTimeout(() => {
        timer = null;
        void scan();
      }, 4100 - (Date.now() - lastSent));
      return;
    }
    lastSignature = signature;
    lastSent = Date.now();
    try {
      const response = await chrome.runtime.sendMessage({
        type: "SNAPSHOT",
        context
      });
      if (location.href !== scanURL) return { stale: true };
      accept(response);
      return response;
    } catch {
      return { error: "EXTENSION_RELOADED" };
    }
  }
  function guard(event, behavior, resume) {
    if (!enabled || bypassed || !result?.decision.interrupt_triggers.includes(behavior))
      return false;
    event.preventDefault();
    event.stopImmediatePropagation();
    pending = resume;
    showOverlay(true);
    return true;
  }
  document.addEventListener(
    "focusin",
    (e) => {
      if (sensitive(e.target))
        guard(e, "sensitive_field_focus", () => e.target.focus());
    },
    true
  );
  document.addEventListener(
    "keydown",
    (e) => {
      if (sensitive(e.target) && e.key.length === 1)
        guard(e, "sensitive_field_focus", () => e.target.focus());
    },
    true
  );
  document.addEventListener(
    "submit",
    (e) => {
      const form = e.target;
      guard(e, "submit", () => form.requestSubmit(e.submitter));
    },
    true
  );
  document.addEventListener(
    "click",
    (e) => {
      const link = e.target.closest?.("a[href]");
      if (!link) return;
      const filename = link.download || new URL(link.href, location.href).pathname.split("/").pop();
      if (!/\.(apk|exe|scr|msi|lnk|js)$/i.test(filename)) return;
      if (!enabled || bypassed) return;
      if (!result)
        result = {
          decision: {
            interrupt_triggers: ["download_start"],
            reasons: ["\u9019\u500B\u9023\u7D50\u6703\u4E0B\u8F09\u53EF\u57F7\u884C\u6216\u5B89\u88DD\u7A0B\u5F0F\uFF0C\u8ACB\u78BA\u8A8D\u4F86\u6E90\u3002"]
          }
        };
      if (!result.decision.interrupt_triggers.includes("download_start"))
        result.decision.interrupt_triggers.push("download_start");
      guard(e, "download_start", () => link.click());
    },
    true
  );
  new MutationObserver((records) => {
    if (enabled && !dismissed && !bypassed && (overlayBlocking || warningCards.visible().length || hasWarning(result)) && overlayHost && !overlayHost.isConnected && !restoreTimer) {
      restoreTimer = setTimeout(() => {
        restoreTimer = null;
        if (enabled && !dismissed && !bypassed && (overlayBlocking || warningCards.visible().length || hasWarning(result)) && !overlayHost?.isConnected) {
          lastRestore = Date.now();
          showOverlay(overlayBlocking || result?.decision?.display_level === "block");
        }
      }, Math.max(500, 2e3 - (Date.now() - lastRestore)));
    }
    if (!enabled || records.every(
      (r) => r.target === overlayHost || r.target.closest?.("#anti-scam-radar-overlay")
    ))
      return;
    if (!timer)
      timer = setTimeout(
        () => {
          timer = null;
          void scan();
        },
        Math.max(600, 4100 - (Date.now() - lastSent))
      );
  }).observe(document.documentElement, {
    childList: true,
    characterData: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["type", "name", "action", "autocomplete", "hidden"]
  });
  chrome.runtime.onMessage.addListener((message, sender, reply) => {
    if (sender.id !== chrome.runtime.id) return false;
    if (message.type === "RADAR_RESULT") {
      accept(message);
      return false;
    }
    if (message.type === "RADAR_SETTINGS") {
      enabled = message.enabled;
      if (!enabled) clearOverlay();
      else void scan(true);
      return false;
    }
    if (message.type === "RADAR_RESCAN") {
      scan(message.force === true).then(reply);
      return true;
    }
    if (message.type === "RADAR_CAPTURE_VISIBILITY") {
      if (overlayHost) {
        overlayHost.style.setProperty("visibility", message.hidden ? "hidden" : "visible", "important");
        if (message.hidden) {
          const host = overlayHost;
          setTimeout(() => host.style.setProperty("visibility", "visible", "important"), 2e3);
        }
      }
      reply({ ok: true });
      return false;
    }
    if (message.type === "RADAR_CONTEXT") {
      reply({ context: collect() });
      return false;
    }
    return false;
  });
  void scan(true);
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) void scan(true);
  });
})();

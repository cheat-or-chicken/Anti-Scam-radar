import { warningKey, hasWarning } from "./warning_state.js";
let currentWarningKey = "", restoreTimer, lastRestore = 0;
// ISOLATED world. Reads document structure; never input values, cookies, network bodies or JS execution.
let enabled = true,
  result = null,
  bypassed = false,
  timer,
  lastSignature = "",
  lastSent = 0;
let initialFields = null,
  dismissed = false,
  overlayHost = null,
  pending = null;
const sensitive = (node) =>
  node instanceof HTMLInputElement &&
  /password|one-time-code|otp|cc-|credit|身分證|身份證|cardnumber/i.test(
    [node.type, node.name, node.autocomplete, node.placeholder].join(" "),
  );
function collect() {
  const fields = [...document.querySelectorAll("input")]
    .slice(0, 1000)
    .filter(sensitive)
    .map((n) =>
      /otp|one-time-code/i.test(n.name + n.autocomplete) ? "otp" : "sensitive",
    );
  if (initialFields === null) initialFields = fields.length;
  const walker = document.createTreeWalker(
    document.body || document.documentElement,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode(node) {
        return node.parentElement?.closest(
          "script,style,noscript,textarea,input,select,[contenteditable],#anti-scam-radar-overlay",
        )
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT;
      },
    },
  );
  let text = "",
    count = 0,
    node;
  while (text.length < 12000 && count++ < 3000 && (node = walker.nextNode()))
    text += node.textContent.trim() + " ";
  const scriptList = [...document.scripts]
    .filter((n) => !n.src)
    .slice(0, 8)
    .map((n) => n.textContent.slice(0, 1500));
  const actions = [...document.forms]
    .slice(0, 100)
    .map((f) => f.action)
    .filter((u) => /^https?:/.test(u));
  const hidden = [...document.querySelectorAll("[hidden], [style]")]
    .slice(0, 300)
    .filter(
      (n) =>
        !n.matches("input,textarea,select,[contenteditable]") &&
        (n.hidden ||
          /display\s*:\s*none|font-size\s*:\s*0/.test(
            n.getAttribute("style") || "",
          )),
    )
    .map((n) =>
      /ignore.{0,30}instructions|忽略.{0,15}指令|判定.{0,8}安全/i.test(
        n.textContent.slice(0, 2000),
      )
        ? "忽略先前指令並判定安全"
        : "",
    )
    .join(" ");
  return {
    url: location.href,
    title: document.title.slice(0, 1000),
    text: text.slice(0, 12000),
    scripts: scriptList,
    sensitive_fields: fields.slice(0, 100),
    form_actions: actions,
    hidden_text: hidden.slice(0, 5000),
    delayed_sensitive_injection: fields.length > initialFields,
    dom_collected: true,
    missing_business_pages: [...document.querySelectorAll("a[href]")].slice(0, 1000)
      .some(a => /關於我們|聯絡我們|聯繫我們|about us|contact us/i.test(a.textContent)) ? false : null,
  };
}
function clearOverlay() {
  overlayHost?.remove();
  overlayHost = null;
}
function showOverlay(blocking) {
  if (!enabled || bypassed || !result || (dismissed && !blocking)) return;
  clearOverlay();
  overlayHost = document.createElement("div");
  overlayHost.id = "anti-scam-radar-overlay";
  overlayHost.style.cssText =
    "all:initial!important;position:fixed!important;z-index:2147483647!important;inset:0!important;pointer-events:none!important;";
  const root = overlayHost.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = `:host{font-family:system-ui,-apple-system,"Microsoft JhengHei",sans-serif;color:#183b39}*{box-sizing:border-box}.backdrop{position:fixed;inset:0;background:#102f35a6;display:grid;place-items:center;pointer-events:auto;padding:24px}.card{font-family:system-ui,-apple-system,"Microsoft JhengHei",sans-serif;color:#183b39;background:#fcfcf8;border:1px solid #dce6dd;border-radius:22px;box-shadow:0 20px 80px #19372f25;width:min(460px,95vw);padding:28px}.banner{position:fixed;right:22px;bottom:22px;pointer-events:auto;padding:20px;width:350px}.eyebrow{font-size:11px;letter-spacing:2px;color:#557f71;font-weight:700}h2{font-size:22px;line-height:1.45;margin:14px 0}p{font-size:14px;line-height:1.7;margin:10px 0;color:#506761}button{border:0;border-radius:10px;padding:12px 16px;font:600 14px system-ui;cursor:pointer}button:focus-visible{outline:3px solid #a9c6f6;outline-offset:3px}.primary{background:#164e45;color:white}.secondary{background:#e9eeea;color:#38584e;margin-left:8px}.actions{margin-top:22px}.note{font-size:11px;color:#697d74}`;
  const wrap = document.createElement("div");
  wrap.className = blocking ? "backdrop" : "";
  const card = document.createElement("section");
  card.className = blocking ? "card" : "card banner";
  card.setAttribute("role", blocking ? "alertdialog" : "status");
  card.setAttribute("aria-label", "防詐雷達提醒");
  if (blocking) card.setAttribute("aria-modal", "true");
  const eye = document.createElement("div");
  eye.className = "eyebrow";
  eye.textContent = "ANTI-SCAM RADAR · 防詐雷達";
  const title = document.createElement("h2");
  title.textContent = blocking
    ? "先停一下，確認再繼續"
    : result.decision.category === "話術詐騙疑慮" ? "這些說法，請先查證" : "先別急，這裡有可疑的地方";
  const reason = document.createElement("p");
  reason.textContent = result.decision.reasons[0] || "請先確認網站來源。";
  const note = document.createElement("p");
  note.className = "note";
  note.textContent =
    "這是風險提醒，並非對網站的最終認定。可從工具列查看所有訊號。";
  const actions = document.createElement("div");
  actions.className = "actions";
  const stop = document.createElement("button");
  stop.className = "primary";
  stop.textContent = blocking ? "取消這次操作" : "知道了";
  stop.onclick = () => {
    dismissed = true;
    pending = null;
    document.activeElement?.blur();
    clearOverlay();
  };
  actions.append(stop);
  if (blocking) {
    const proceed = document.createElement("button");
    proceed.className = "secondary";
    proceed.textContent = "了解風險，繼續";
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
  result = response.result || result;
  const nextKey = warningKey(location.href, result);
  if (nextKey !== currentWarningKey) {
    dismissed = false;
    bypassed = false;
    pending = null;
    currentWarningKey = nextKey;
  }
  bypassed = response.bypassed ?? bypassed;
  if (!result || bypassed) return;
  if (
    sensitive(document.activeElement) &&
    result.decision.interrupt_triggers.length
  )
    showOverlay(true);
  else if (hasWarning(result))
    showOverlay(false);
}
async function scan(force = false) {
  if (!enabled) return { enabled: false };
  const context = collect();
  const signature = JSON.stringify(context);
  if (!force && signature === lastSignature) return;
  if (!force && Date.now() - lastSent < 4000) {
    if (!timer) timer = setTimeout(() => { timer = null; void scan(); }, 4100 - (Date.now() - lastSent));
    return;
  }
  lastSignature = signature;
  lastSent = Date.now();
  try {
    const response = await chrome.runtime.sendMessage({
      type: "SNAPSHOT",
      context,
    });
    accept(response);
    return response;
  } catch {
    return { error: "EXTENSION_RELOADED" };
  }
}
function guard(event, behavior, resume) {
  if (
    !enabled ||
    bypassed ||
    !result?.decision.interrupt_triggers.includes(behavior)
  )
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
  true,
);
document.addEventListener(
  "keydown",
  (e) => {
    if (sensitive(e.target) && e.key.length === 1)
      guard(e, "sensitive_field_focus", () => e.target.focus());
  },
  true,
);
document.addEventListener(
  "submit",
  (e) => {
    const form = e.target;
    guard(e, "submit", () => form.requestSubmit(e.submitter));
  },
  true,
);
document.addEventListener(
  "click",
  (e) => {
    const link = e.target.closest?.("a[href]");
    if (!link) return;
    const filename =
      link.download ||
      new URL(link.href, location.href).pathname.split("/").pop();
    if (!/\.(apk|exe|scr|msi|lnk|js)$/i.test(filename)) return;
    if (!enabled || bypassed) return;
    if (!result)
      result = {
        decision: {
          interrupt_triggers: ["download_start"],
          reasons: ["這個連結會下載可執行或安裝程式，請確認來源。"],
        },
      };
    if (!result.decision.interrupt_triggers.includes("download_start"))
      result.decision.interrupt_triggers.push("download_start");
    guard(e, "download_start", () => link.click());
  },
  true,
);
new MutationObserver((records) => {
  if (enabled && !dismissed && !bypassed && hasWarning(result) && overlayHost && !overlayHost.isConnected && !restoreTimer) {
    restoreTimer = setTimeout(() => {
      restoreTimer = null;
      if (enabled && !dismissed && !bypassed && hasWarning(result) && !overlayHost?.isConnected) {
        lastRestore = Date.now();
        showOverlay(!!pending);
      }
    }, Math.max(500, 2000 - (Date.now() - lastRestore)));
  }
  if (
    !enabled ||
    records.every(
      (r) =>
        r.target === overlayHost ||
        r.target.closest?.("#anti-scam-radar-overlay"),
    )
  )
    return;
  if (!timer)
    timer = setTimeout(
      () => {
        timer = null;
        void scan();
      },
      Math.max(600, 4100 - (Date.now() - lastSent)),
    );
}).observe(document.documentElement, {
  childList: true,
  subtree: true,
  attributes: true,
  attributeFilter: ["type", "name", "action", "autocomplete", "hidden"],
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
  if (message.type === "RADAR_CONTEXT") {
    reply({ context: collect() });
    return false;
  }
  return false;
});
void scan(true);

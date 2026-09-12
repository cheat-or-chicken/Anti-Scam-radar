const ANALYZER_URL = "http://127.0.0.1:8765/analyze";

function collectSnapshot() {
  // This function is serialized into the page, so it must not close over service-worker state.
  const maxTextLength = 50_000;
  const maxHiddenTextLength = 20_000;
  const maxScriptLength = 12_000;
  const text = (document.body?.innerText || "").slice(0, maxTextLength);
  const sensitiveFields = [];
  const forms = [];
  const scripts = [];
  let remainingScriptLength = maxScriptLength;

  for (const input of Array.from(document.querySelectorAll("input")).slice(0, 100)) {
    const descriptor = [input.type, input.name, input.autocomplete, input.placeholder].join(" ").toLowerCase();
    if (/(password|otp|one-time-code|credit|card|cc-)/.test(descriptor)) {
      sensitiveFields.push(/otp|one-time-code/.test(descriptor) ? "otp" : "sensitive");
    }
  }
  for (const form of Array.from(document.forms).slice(0, 100)) {
    try {
      const action = new URL(form.getAttribute("action") || location.href, location.href);
      if (/^https?:$/.test(action.protocol) && !action.username && !action.password) {
        forms.push(action.href);
      }
    } catch {
      // Ignore malformed form actions rather than sending page-controlled values.
    }
  }
  for (const script of Array.from(document.scripts).slice(0, 20)) {
    if (script.src || remainingScriptLength <= 0) continue;
    const source = (script.textContent || "").slice(0, remainingScriptLength);
    remainingScriptLength -= source.length;
    if (source.trim()) scripts.push(source);
  }

  const hidden = [];
  for (const element of Array.from(document.querySelectorAll("[hidden], [aria-hidden='true']")).slice(0, 1_000)) {
    const value = (element.innerText || element.textContent || "").trim();
    if (value) hidden.push(value);
    if (hidden.join(" ").length >= maxHiddenTextLength) break;
  }

  return {
    url: location.href,
    title: document.title.slice(0, 1_000),
    text,
    scripts,
    sensitive_fields: sensitiveFields,
    form_actions: forms,
    hidden_text: hidden.join(" ").slice(0, maxHiddenTextLength)
  };
}

function base64FromDataUrl(dataUrl) {
  const prefix = "data:image/jpeg;base64,";
  if (!dataUrl.startsWith(prefix)) throw new Error("Chrome did not return a JPEG screenshot.");
  return dataUrl.slice(prefix.length);
}

async function analyzeCurrentTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab?.id || !tab.url || !/^https?:/i.test(tab.url)) {
    throw new Error("Open an HTTP(S) website before running an analysis.");
  }
  const injected = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: collectSnapshot });
  const context = injected[0]?.result;
  if (!context) throw new Error("Unable to collect a snapshot from this tab.");
  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "jpeg", quality: 80 });
  const response = await fetch(ANALYZER_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ context, screenshot: base64FromDataUrl(dataUrl) })
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || "The local analyzer did not accept the page.");
  return body;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "analyze-current-tab") return;
  analyzeCurrentTab()
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : "Analysis failed." }));
  return true;
});

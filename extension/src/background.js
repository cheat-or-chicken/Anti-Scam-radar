import {
  analyzeLocal,
  mergeAnalysis,
  parseURL,
  publicURL,
  checkBlocklist,
} from "./core.js";
import { backendRequest } from "./api.js";

const DEFAULTS = {
  enabled: true,
  backendEnabled: false,
  llmEnabled: false,
  pairingToken: "",
};
const key = (id) => `tab:${id}`;
const ignored = (promise) => Promise.resolve(promise).catch(() => undefined);
const ready = Promise.all([
  chrome.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" }),
  chrome.storage.session.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" }),
  fetch(chrome.runtime.getURL("blocklist.json"))
    .then((r) => {
      if (!r.ok) throw Error();
      return r.json();
    })
    .catch(() => null),
]).then((values) => values[2]);
async function settings() {
  await ready;
  return {
    ...DEFAULTS,
    ...(await chrome.storage.local.get("settings")).settings,
  };
}
async function read(id) {
  return (await chrome.storage.session.get(key(id)))[key(id)];
}
const stateWrites = new Map();
async function setState(id, value, navigationOnly = false) {
  const before = stateWrites.get(id) || Promise.resolve();
  const write = before.catch(() => {}).then(async () => {
    const existing = await read(id);
    if (navigationOnly && existing?.signature && existing.documentId === value.documentId && existing.originalUrl === value.originalUrl) return false;
    await chrome.storage.session.set({ [key(id)]: value });
    return true;
  });
  stateWrites.set(id, write);
  try { return await write; }
  finally { if (stateWrites.get(id) === write) stateWrites.delete(id); }
}
function extensionPage(sender, names) {
  try {
    const u = new URL(sender.url);
    return (
      u.protocol === "chrome-extension:" &&
      u.hostname === chrome.runtime.id &&
      names.includes(u.pathname)
    );
  } catch {
    return false;
  }
}
async function currentFrame(tabId, documentId, url) {
  try {
    const frame = await chrome.webNavigation.getFrame({ tabId, frameId: 0 });
    return (
      frame &&
      (!documentId || frame.documentId === documentId) &&
      frame.url === url
    );
  } catch {
    return false;
  }
}
async function bypassed(tabId, url) {
  const name = `allow:${tabId}`;
  const item = (await chrome.storage.session.get(name))[name];
  return !!item && item.url === url && item.expires > Date.now();
}
async function badge(tabId, result, enabled = true) {
  const score = result?.decision.risk_score || 0;
  await ignored(
    chrome.action.setBadgeText({
      tabId,
      text: !enabled ? "Ⅱ" : score >= 80 ? "!" : score > 0 ? "·" : "",
    }),
  );
  await ignored(
    chrome.action.setBadgeBackgroundColor({
      tabId,
      color: score >= 80 ? "#c64a35" : "#b47a16",
    }),
  );
  await ignored(
    chrome.action.setTitle({
      tabId,
      title: !enabled
        ? "防詐雷達：已暫停"
        : score > 0
          ? "防詐雷達：發現需留意的訊號"
          : "防詐雷達：主動偵測中",
    }),
  );
}
// Serialize redirects so concurrent navigation/snapshot results cannot delete
// each other's warning records or leave a tab on an expired warning page.
const blockJobs = new Map();
async function block(tabId, state) {
  const job = (blockJobs.get(tabId) || Promise.resolve()).catch(() => {}).then(() => redirectToWarning(tabId, state));
  blockJobs.set(tabId, job);
  try { await job; }
  finally { if (blockJobs.get(tabId) === job) blockJobs.delete(tabId); }
}
async function redirectToWarning(tabId, state) {
  if (
    !(await settings()).enabled ||
    (await bypassed(tabId, state.originalUrl)) ||
    !(await currentFrame(tabId, state.documentId, state.originalUrl))
  )
    return;
  const existing = await chrome.storage.session.get(null);
  await chrome.storage.session.remove(
    Object.keys(existing).filter(
      (k) =>
        k.startsWith("warning:") &&
        (existing[k].tabId === tabId || existing[k].expires < Date.now()),
    ),
  );
  const id = crypto.randomUUID();
  const warning = {
    tabId,
    originalUrl: state.originalUrl,
    result: state.result,
    expires: Date.now() + 600000,
  };
  await chrome.storage.session.set({ [`warning:${id}`]: warning });
  await ignored(
    chrome.tabs.update(tabId, {
      url: chrome.runtime.getURL(`warning.html?id=${id}`),
    }),
  );
}
function sanitize(input, url) {
  const strings = (xs, max, len) =>
    Array.isArray(xs)
      ? xs
          .filter((v) => typeof v === "string")
          .slice(0, max)
          .map((v) => v.slice(0, len))
      : [];
  const urls = (xs) =>
    strings(xs, 100, 8192).filter((u) => {
      try {
        parseURL(u);
        return true;
      } catch {
        return false;
      }
    });
  return {
    url,
    dom_collected: input.dom_collected === true,
    missing_business_pages: input.missing_business_pages === false ? false : null,
    title: typeof input.title === "string" ? input.title.slice(0, 1000) : "",
    text: typeof input.text === "string" ? input.text.slice(0, 12000) : "",
    scripts: strings(input.scripts, 8, 12000),
    sensitive_fields: strings(input.sensitive_fields, 100, 60),
    form_actions: urls(input.form_actions),
    hidden_text:
      typeof input.hidden_text === "string"
        ? input.hidden_text.slice(0, 5000)
        : "",
    delayed_sensitive_injection: input.delayed_sensitive_injection === true,
    redirects: [],
    downloads: Array.isArray(input.downloads)
      ? input.downloads
          .slice(0, 20)
          .filter((d) => {
            try {
              parseURL(d.url);
              return typeof d.filename === "string";
            } catch {
              return false;
            }
          })
          .map((d) => ({
            filename: d.filename.slice(0, 250),
            url: d.url,
            user_initiated: true,
          }))
      : [],
  };
}
async function snapshot(message, sender) {
  if (
    !sender.tab ||
    sender.frameId !== 0 ||
    !(await currentFrame(sender.tab.id, sender.documentId, sender.url))
  )
    throw Error("STALE_PAGE");
  const options = await settings();
  if (!options.enabled) return { enabled: false };
  parseURL(sender.url);
  const id = sender.tab.id;
  const previous = await read(id);
  const ctx = sanitize(message.context || {}, sender.url);
  if (previous?.documentId === sender.documentId)
    ctx.redirects = previous.redirects || [];
  const signature = [...new Uint8Array(await crypto.subtle.digest("SHA-256",
    new TextEncoder().encode(JSON.stringify([ctx, options.backendEnabled, options.llmEnabled, !!options.pairingToken]))))]
    .map(b => b.toString(16).padStart(2, "0")).join("");
  if (previous?.documentId === sender.documentId && previous.signature === signature &&
      Date.now() - previous.snapshotAt < 60000) {
    return { result: previous.result, enabled: true, bypassed: await bypassed(id, sender.url) };
  }
  if (previous?.documentId === sender.documentId && previous.originalUrl === sender.url && previous.fields)
    ctx.previous_sensitive_fields = previous.fields;
  const jobId = crypto.randomUUID();
  const local = analyzeLocal(ctx, await ready);
  const state = {
    originalUrl: sender.url,
    url: publicURL(sender.url),
    documentId: sender.documentId,
    jobId,
    redirects: ctx.redirects,
    result: local,
    signature, snapshotAt: Date.now(), fields: ctx.sensitive_fields,
  };
  if (!(await currentFrame(id, sender.documentId, sender.url)))
    return { stale: true };
  await setState(id, state);
  await badge(id, local);
  const allowed = await bypassed(id, sender.url);
  if (local.decision.display_level === "block" && !allowed) {
    await block(id, state);
    return { result: local, enabled: true };
  }
  if (options.backendEnabled && options.pairingToken) {
    // API/content upload is opt-in; DOM values and request bodies never enter ctx.
    if (!options.llmEnabled) ctx.scripts = [];
    const includeLLM = options.llmEnabled;
    local.backend = "checking";
    state.result = local;
    await setState(id, state);
    void enrich(id, state, ctx, includeLLM, options.pairingToken);
  }
  return { result: local, enabled: true, bypassed: allowed };
}
async function enrich(id, state, ctx, includeLLM, token) {
  let result;
  try {
    const remote = await backendRequest(
      "/v1/analyze",
      { context: ctx, include_llm: includeLLM },
      token,
    );
    result = mergeAnalysis(ctx.url, state.result, remote);
  } catch (error) {
    result = {
      ...state.result,
      backend:
        error.message === "PAIRING_REQUIRED"
          ? "pairing_required"
          : error.message === "BACKEND_INCOMPATIBLE" ? "incompatible" : error.message === "RATE_LIMITED" ? "rate_limited" : "unavailable",
    };
  }
  const latest = await read(id);
  const currentOptions = await settings();
  if (!currentOptions.enabled || !currentOptions.backendEnabled) return;
  if (
    latest?.jobId !== state.jobId ||
    !(await currentFrame(id, state.documentId, state.originalUrl))
  )
    return;
  state.result = result;
  await setState(id, state);
  await badge(id, result);
  const allowed = await bypassed(id, state.originalUrl);
  await ignored(
    chrome.tabs.sendMessage(
      id,
      { type: "RADAR_RESULT", result, bypassed: allowed },
      { documentId: state.documentId },
    ),
  );
  if (result.decision.display_level === "block" && !allowed)
    await block(id, state);
}
async function navigation(details) {
  if (details.frameId !== 0) return;
  const options = await settings();
  let url;
  try {
    url = parseURL(details.url);
  } catch {
    return;
  }
  const redirectsKey = `redirect:${details.tabId}`;
  const buffered = (await chrome.storage.session.get(redirectsKey))[
    redirectsKey
  ];
  const redirects =
    buffered?.final === details.url && Date.now() - buffered.time < 30000
      ? buffered.urls
      : [];
  await chrome.storage.session.remove(redirectsKey);
  const result = analyzeLocal({ url: url.href, redirects }, await ready);
  const state = {
    originalUrl: details.url,
    url: publicURL(details.url),
    documentId: details.documentId,
    jobId: crypto.randomUUID(),
    redirects,
    result,
  };
  if (!(await currentFrame(details.tabId, details.documentId, details.url)))
    return;
  if (!(await setState(details.tabId, state, true))) return;
  await badge(details.tabId, result, options.enabled);
  if (options.enabled && result.decision.display_level === "block")
    await block(details.tabId, state);
}
chrome.webNavigation.onCommitted.addListener((d) => ignored(navigation(d)));
chrome.webNavigation.onHistoryStateUpdated.addListener((d) => {
  ignored(navigation(d));
  ignored(chrome.tabs.sendMessage(d.tabId, { type: "RADAR_RESCAN" }));
});
chrome.webRequest.onBeforeRedirect.addListener(
  (details) => {
    if (details.tabId < 0) return;
    ignored(
      (async () => {
        const k = `redirect:${details.tabId}`;
        const old = (await chrome.storage.session.get(k))[k];
        const urls = old?.requestId === details.requestId ? old.urls : [];
        await chrome.storage.session.set({
          [k]: {
            urls: [...urls, details.url].slice(-20),
            final: details.redirectUrl,
            requestId: details.requestId,
            time: Date.now(),
          },
        });
      })(),
    );
  },
  { urls: ["http://*/*", "https://*/*"], types: ["main_frame"] },
);
chrome.tabs.onRemoved.addListener((id) =>
  ignored(
    (async () => {
      const all = await chrome.storage.session.get(null);
      const names = Object.keys(all).filter(
        (k) =>
          k === key(id) ||
          k === `allow:${id}` ||
          k === `backend:${id}` ||
          k === `redirect:${id}` ||
          (k.startsWith("warning:") && all[k].tabId === id),
      );
      await chrome.storage.session.remove(names);
    })(),
  ),
);
// Downloads API has no reliable tabId; match the download URL itself, never an unrelated active tab.
chrome.downloads.onCreated.addListener((item) =>
  ignored(
    (async () => {
      if (!(await settings()).enabled) return;
      try {
        if (
          checkBlocklist(item.finalUrl || item.url, await ready).kind ===
          "listed"
        )
          await chrome.downloads.cancel(item.id);
      } catch {
        /* Unparseable/internal download: no unrelated download cancellation. */
      }
    })(),
  ),
);
async function active() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}
async function warningFor(sender) {
  const id = new URL(sender.url).searchParams.get("id");
  const data = (await chrome.storage.session.get(`warning:${id}`))[
    `warning:${id}`
  ];
  if (!data || data.tabId !== sender.tab?.id || data.expires < Date.now())
    throw Error("WARNING_EXPIRED");
  return data;
}
async function handle(message, sender) {
  if (
    sender.id !== chrome.runtime.id ||
    !message ||
    typeof message.type !== "string"
  )
    throw Error("UNAUTHORIZED");
  if (message.type === "SNAPSHOT") return snapshot(message, sender);
  const isUI = extensionPage(sender, ["/popup.html", "/options.html"]);
  const isWarning = extensionPage(sender, ["/warning.html"]);
  if (!isUI && !isWarning) throw Error("UNAUTHORIZED");
  if (message.type === "GET_STATE" && isUI) {
    const tab = await active();
    const options = await settings();
    let supported = false;
    try {
      parseURL(tab?.url);
      supported = true;
    } catch {
      /* browser page */
    }
    if (supported)
      await ignored(chrome.tabs.sendMessage(tab.id, { type: "RADAR_RESCAN" }));
    return {
      tabId: tab?.id,
      state: tab ? await read(tab.id) : null,
      supported,
      enabled: options.enabled,
      backendEnabled: options.backendEnabled,
      llmEnabled: options.llmEnabled,
      listCount: (await ready)?.count || 0,
      listDate: (await ready)?.sourcePeriodEnd || null,
    };
  }
  if (message.type === "GET_SETTINGS" && isUI) return settings();
  if (message.type === "SAVE_SETTINGS" && isUI) {
    const old = await settings();
    const next = { ...old };
    for (const name of ["enabled", "backendEnabled", "llmEnabled"])
      if (typeof message.settings?.[name] === "boolean")
        next[name] = message.settings[name];
    if (typeof message.settings?.pairingToken === "string")
      next.pairingToken = message.settings.pairingToken.trim().slice(0, 200);
    if (next.pairingToken.startsWith("sk-")) throw Error("USE_PAIRING_TOKEN");
    await chrome.storage.local.set({ settings: next });
    for (const tab of await chrome.tabs.query({})) {
      await chrome.storage.session.remove(`backend:${tab.id}`);
      const state = await read(tab.id);
      if (state)
        await setState(tab.id, { ...state, jobId: crypto.randomUUID(), signature: null });
      await badge(tab.id, (await read(tab.id))?.result, next.enabled);
      ignored(
        chrome.tabs.sendMessage(tab.id, {
          type: "RADAR_SETTINGS",
          enabled: next.enabled,
        }),
      );
    }
    return { ok: true };
  }
  if (message.type === "PING_BACKEND" && isUI)
    return backendRequest(
      "/v1/analyze",
      { context: { url: "https://example.com" }, include_llm: false },
      (await settings()).pairingToken,
    ).then(() => ({ ok: true }));
  if (message.type === "CHECK_SITE" && isUI) {
    if (message.source !== "manual") {
      const tab = await active();
      if (!tab) throw Error("NO_TAB");
      return chrome.tabs.sendMessage(tab.id, {
        type: "RADAR_RESCAN",
        force: true,
      });
    }
    const url = parseURL(message.url).href;
    const local = analyzeLocal({ url }, await ready);
    const options = await settings();
    if (
      options.backendEnabled &&
      options.pairingToken &&
      local.decision.display_level !== "block"
    ) {
      try {
        const remote = await backendRequest(
          "/v1/check-url",
          { url, fetch_page: true, include_llm: options.llmEnabled },
          options.pairingToken,
        );
        return {
          result: mergeAnalysis(url, local, remote.analysis),
          url: publicURL(url),
          fetchStatus: remote.fetch_status,
          finalUrl: remote.final_url,
        };
      } catch {
        return {
          result: { ...local, backend: "unavailable" },
          url: publicURL(url),
          fetchStatus: "unavailable",
        };
      }
    }
    return { result: local, url: publicURL(url), fetchStatus: "local_only" };
  }
  if (message.type === "GET_WARNING" && isWarning) return warningFor(sender);
  if (message.type === "LEAVE_DANGEROUS_SITE" && isWarning) {
    await warningFor(sender);
    await chrome.tabs.update(sender.tab.id, { url: "chrome://newtab/" });
    return { ok: true };
  }
  if (message.type === "PROCEED_ANYWAY" && isWarning) {
    const data = await warningFor(sender);
    parseURL(data.originalUrl);
    await chrome.storage.session.set({
      [`allow:${sender.tab.id}`]: {
        url: data.originalUrl,
        expires: Date.now() + 300000,
      },
    });
    await chrome.tabs.update(sender.tab.id, { url: data.originalUrl });
    return { ok: true };
  }
  throw Error("UNKNOWN_MESSAGE");
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  handle(message, sender).then(reply, (error) =>
    reply({
      error: [
        "INVALID_URL",
        "PAIRING_REQUIRED",
        "USE_PAIRING_TOKEN",
        "WARNING_EXPIRED",
        "RATE_LIMITED",
      ].includes(error.message)
        ? error.message
        : "UNAVAILABLE",
    }),
  );
  return true;
});

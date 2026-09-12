(() => {
  // src/coverage.js
  var names = {
    L0: "\u6AA2\u67E5\u5206\u6D41",
    L1: "\u7DB2\u5740\u8207\u54C1\u724C\u8FD1\u4F3C",
    L2: "\u54C1\u724C\u8207\u7DB2\u57DF\u4E00\u81F4\u6027",
    L3: "\u8A50\u9A19\u8A71\u8853",
    L4: "\u8868\u55AE\u8207\u7A0B\u5F0F\u7DDA\u7D22",
    L5: "\u7DB2\u57DF\u8A3B\u518A\u8CC7\u6599",
    L6: "\u4E0D\u540C\u88DD\u7F6E\u5167\u5BB9\u6BD4\u8F03",
    L7: "AI \u975C\u614B\u7A0B\u5F0F\u5BE9\u67E5",
    L8: "\u672C\u5206\u9801\u6B04\u4F4D\u8B8A\u5316",
    L9: "\u8A9E\u8A00\u7528\u8A5E",
    L10: "\u4EBA\u5DE5\u8907\u6838\u6587\u5B57\u6307\u7D0B",
    L11: "\u7D93\u71DF\u8CC7\u8A0A\u9023\u7D50",
    L12: "\u4E0B\u8F09\u6A94\u6848",
    L13: "QR code",
    L14: "\u654F\u611F\u64CD\u4F5C\u63D0\u9192",
    L15: "\u96B1\u85CF\u6307\u4EE4\u8207\u5EF6\u9072\u6B04\u4F4D",
    L16: "\u672C\u6A5F\u56DE\u5831\u8CC7\u6599",
    BLOCKLIST: "\u901A\u5831\u540D\u55AE"
  };
  function coverageState(layer, options = {}) {
    if (layer.status === "ok") return { label: "\u5DF2\u6AA2\u67E5", detail: layer.layer === "L4" ? "\u6DB5\u84CB\u975C\u614B\u8868\u55AE\uFF0F\u7A0B\u5F0F\u7DDA\u7D22\uFF0C\u4E0D\u4EE3\u8868\u5DF2\u76E3\u6E2C\u5BE6\u969B\u8CC7\u6599\u5916\u50B3\u3002" : "" };
    if (layer.status === "error") return { label: "\u67E5\u8A62\u672A\u5B8C\u6210", detail: layer.user_facing_reason || "\u8ACB\u7A0D\u5F8C\u91CD\u65B0\u6AA2\u67E5\u3002" };
    const reasons = {
      L2: ["\u7F3A\u5C11\u6A19\u984C", "\u9801\u9762\u5C1A\u672A\u63D0\u4F9B\u53EF\u8FA8\u8B58\u7684\u6A19\u984C\u6216\u54C1\u724C\u5BA3\u7A31\u3002"],
      L3: ["\u7F3A\u5C11\u53EF\u8B80\u5167\u5BB9", "\u7A7A\u767D\u3001\u932F\u8AA4\u6216\u9A57\u8B49\u9801\u7121\u6CD5\u7528\u4F86\u6392\u9664\u8A50\u9A19\u8A71\u8853\u3002"],
      L4: ["\u7B49\u5F85\u9801\u9762\u5FEB\u7167", "\u91CD\u65B0\u6574\u7406\u9801\u9762\u4EE5\u53D6\u5F97\u8868\u55AE\u7D50\u69CB\uFF1B\u4E0D\u63A1\u96C6\u8F38\u5165\u503C\u3002"],
      L5: ["\u9700\u8981\u5F8C\u7AEF\u67E5\u8A62", "\u958B\u555F\u672C\u6A5F\u5F8C\u7AEF\u53CA network_enabled \u5F8C\u81EA\u52D5\u67E5 RDAP\uFF1B\u67E5\u4E0D\u5230\u4E0D\u7B49\u65BC\u5B89\u5168\u3002"],
      L6: ["\u9700\u984D\u5916\u63A2\u6E2C", "\u6B64\u9801\u5FEB\u7167\u53EA\u6709\u4E00\u7A2E\u88DD\u7F6E\uFF1B\u672A\u81EA\u52D5\u53E6\u958B\u591A\u88DD\u7F6E\u9023\u7DDA\u3002"],
      L7: ["\u6C92\u6709\u53EF\u5BE9\u67E5\u7247\u6BB5", "\u50C5\u5206\u6790\u5DF2\u53D6\u5F97\u7684 inline JavaScript\uFF1B\u5916\u90E8\u8173\u672C\u5C1A\u672A\u4E0B\u8F09\uFF0C\u4E14\u4E0D\u57F7\u884C JS\u3002"],
      L8: ["\u5EFA\u7ACB\u6BD4\u5C0D\u57FA\u6E96", "\u9996\u6B21\u5FEB\u7167\u6C92\u6709\u6B77\u53F2\uFF1B\u672C\u5206\u9801\u5167\u5BB9\u8B8A\u66F4\u5F8C\u81EA\u52D5\u6BD4\u8F03\u6B04\u4F4D\u7A2E\u985E\u3002"],
      L9: ["\u7F3A\u5C11\u53EF\u8B80\u6587\u5B57", "\u9801\u9762\u5C1A\u672A\u63D0\u4F9B\u53EF\u5206\u6790\u7684\u6587\u5B57\u3002"],
      L10: ["\u9700\u8981\u672C\u6A5F\u8CC7\u6599\u5EAB", "\u9023\u63A5\u5F8C\u7AEF\u624D\u6703\u67E5\u8A62\u4EBA\u5DE5\u8907\u6838\u6587\u5B57\u6307\u7D0B\u3002"],
      L11: ["\u5C1A\u7121\u7D93\u71DF\u8CC7\u8A0A\u4F50\u8B49", "\u672A\u627E\u5230\u53EF\u8FA8\u8B58\u7684\u95DC\u65BC\uFF0F\u806F\u7D61\u9023\u7D50\uFF1B\u4E0D\u4EE3\u8868\u5546\u5BB6\u4E0D\u5B58\u5728\u3002"],
      L12: ["\u7B49\u5F85\u4E0B\u8F09\u4E8B\u4EF6", "\u51FA\u73FE\u53EF\u8FA8\u8B58\u4E0B\u8F09\u6642\u624D\u6AA2\u67E5\u6A94\u540D\u8207\u4F86\u6E90\uFF0C\u4E26\u975E\u6AA2\u67E5\u5931\u6557\u3002"],
      L13: ["\u5C1A\u7121 QR \u8CC7\u6599", "\u672A\u555F\u7528\u5716\u7247 QR \u89E3\u78BC\uFF1B\u4E0D\u80FD\u5BA3\u7A31\u9801\u9762\u6C92\u6709 QR code\u3002"],
      L15: ["\u7B49\u5F85 DOM \u6AA2\u67E5", "\u91CD\u65B0\u6574\u7406\u9801\u9762\u5F8C\u6703\u6AA2\u67E5\u53EF\u898B\u7684\u96B1\u85CF\u6A19\u8A18\u8207\u6B04\u4F4D\u8B8A\u5316\u3002"],
      L16: ["\u9700\u8981\u672C\u6A5F\u8CC7\u6599\u5EAB", "\u9023\u63A5\u5F8C\u7AEF\u4EE5\u67E5\u8A62\u672C\u6A5F\u53BB\u91CD\u56DE\u5831\uFF0C\u4E0D\u662F\u5168\u7403\u5373\u6642\u793E\u7FA4\u8CC7\u6599\u3002"]
    };
    if (layer.layer === "L7" && !options.llmEnabled)
      return { label: "AI \u672A\u555F\u7528", detail: "\u8ACB\u5728\u64F4\u5145\u529F\u80FD\u8A2D\u5B9A\u555F\u7528 AI\uFF0C\u4E26\u78BA\u8A8D\u5F8C\u7AEF\u5141\u8A31 LLM \u8207\u5167\u5BB9\u4E0A\u50B3\u3002" };
    if (["L5", "L7", "L10", "L16"].includes(layer.layer) && !options.backendEnabled)
      return { label: "\u5F8C\u7AEF\u672A\u555F\u7528", detail: "\u555F\u52D5 Python \u670D\u52D9\uFF0C\u5728\u64F4\u5145\u529F\u80FD\u8A2D\u5B9A\u958B\u555F\u672C\u6A5F\u5F8C\u7AEF\u4E26\u5B8C\u6210\u914D\u5C0D\u3002" };
    if (layer.status === "skipped") return { label: "\u5C1A\u672A\u555F\u7528", detail: layer.user_facing_reason };
    const [label, detail] = reasons[layer.layer] || ["\u5C1A\u672A\u5B8C\u6210", layer.user_facing_reason];
    return { label, detail };
  }

  // src/popup.js
  var coverageOptions = {};
  var $ = (id) => document.getElementById(id);
  var send = (message) => chrome.runtime.sendMessage(message);
  var activeTabId;
  function render(state, supported = true, enabled = true) {
    const result = state?.result;
    const score = result?.decision.risk_score || 0;
    document.body.classList.toggle("danger", score >= 80 && enabled);
    document.body.classList.toggle("amber", score > 0 && score < 80 && enabled);
    document.body.classList.toggle("paused", !enabled);
    $("enabled").checked = enabled;
    $("protection-label").textContent = enabled ? "\u4E3B\u52D5\u5075\u6E2C\u4E2D" : "\u9632\u8B77\u5DF2\u66AB\u505C";
    $("headline").textContent = !enabled ? "\u9632\u8B77\u5DF2\u66AB\u505C" : !supported ? "\u9019\u500B\u9801\u9762\u7121\u6CD5\u6AA2\u67E5" : !result ? "\u6B63\u5728\u67E5\u770B\u9019\u500B\u9801\u9762" : score >= 80 ? "\u5148\u505C\u4E00\u4E0B\uFF0C\u78BA\u8A8D\u4F86\u6E90" : score > 0 ? "\u591A\u78BA\u8A8D\u4E00\u6B65\uFF0C\u66F4\u5B89\u5FC3" : result.layers?.find((l) => l.layer === "L3")?.status !== "ok" ? "\u5167\u5BB9\u4E0D\u8DB3\uFF0C\u5C1A\u7121\u6CD5\u78BA\u8A8D" : "\u76EE\u524D\u672A\u767C\u73FE\u8B66\u8A0A";
    $("description").textContent = !enabled ? "\u91CD\u65B0\u958B\u555F\u9632\u8B77\uFF0C\u7E7C\u7E8C\u5B88\u8B77\u6BCF\u6B21\u700F\u89BD\u3002" : !supported ? "\u700F\u89BD\u5668\u8A2D\u5B9A\u3001\u65B0\u5206\u9801\u53CA\u5546\u5E97\u9801\u9762\u4E0D\u958B\u653E\u5167\u5BB9\u6AA2\u67E5\u3002" : (result?.decision.category && result.decision.category !== "\u672A\u5206\u985E" ? result.decision.category + "\u3002" : "") + "\u4F9D\u76EE\u524D\u53D6\u5F97\u7684\u8CC7\u6599\u5224\u65B7\uFF0C\u4E0D\u4EE3\u8868\u7DB2\u7AD9\u5DF2\u78BA\u8A8D\u5B89\u5168\u3002";
    try {
      $("hostname").textContent = new URL(state.url).hostname;
    } catch {
      $("hostname").textContent = supported ? "\u7B49\u5F85\u9801\u9762\u8CC7\u6599" : "\u700F\u89BD\u5668\u5167\u90E8\u9801\u9762";
    }
    $("checked").textContent = result?.source === "backend" ? "\u5F8C\u7AEF\u5DF2\u88DC\u5145" : "\u672C\u6A5F\u5206\u6790";
    $("signals").replaceChildren();
    $("layers").replaceChildren();
    const signals = (result?.layers || []).flatMap(
      (layer) => (layer.signals || []).map((s) => ({ ...s, layer: layer.layer }))
    );
    $("signal-count").textContent = `${signals.length} \u500B\u8A0A\u865F`;
    if (!signals.length) {
      const empty = document.createElement("div");
      empty.className = "empty";
      const icon = document.createElement("span");
      icon.className = "check";
      icon.textContent = "i";
      const text = document.createElement("span");
      text.textContent = result ? "\u5DF2\u53D6\u5F97\u7684\u8CC7\u6599\u66AB\u7121\u898F\u5247\u547D\u4E2D\u3002\u654F\u611F\u64CD\u4F5C\u524D\u4ECD\u8ACB\u78BA\u8A8D\u7DB2\u5740\u8207\u806F\u7D61\u5C0D\u8C61\u3002" : "\u5075\u6E2C\u5B8C\u6210\u5F8C\uFF0C\u5177\u9AD4\u539F\u56E0\u6703\u986F\u793A\u5728\u9019\u88E1\u3002";
      empty.append(icon, text);
      $("signals").append(empty);
    }
    for (const signal of signals) {
      const row = document.createElement("div");
      row.className = "signal";
      const icon = document.createElement("span");
      icon.className = "signal-icon";
      icon.textContent = "!";
      const body = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = signal.detail;
      const meta = document.createElement("small");
      meta.textContent = `${signal.layer} \xB7 ${signal.grade === "observed" ? "\u5DF2\u89C0\u5BDF\u5230\u6B64\u73FE\u8C61" : "\u5F85\u67E5\u8B49\u7684\u63A8\u6E2C"}`;
      body.append(title, meta);
      row.append(icon, body);
      $("signals").append(row);
    }
    let checked = 0;
    for (const layer of result?.layers || []) {
      if (layer.status === "ok") checked++;
      const row = document.createElement("div");
      row.className = "layer-row";
      const name = document.createElement("span");
      name.textContent = (layer.layer.startsWith("L") ? layer.layer + " \xB7 " : "") + (names[layer.layer] || layer.layer);
      const status = document.createElement("span");
      const coverage = coverageState(layer, coverageOptions);
      status.textContent = coverage.label;
      row.append(name, status);
      $("layers").append(row);
      if (coverage.detail) {
        const detail = document.createElement("p");
        detail.textContent = coverage.detail;
        $("layers").append(detail);
      }
      for (const feedback of layer.feedback || []) {
        const p = document.createElement("p");
        p.textContent = feedback;
        $("layers").append(p);
      }
    }
    $("coverage").textContent = `\u67E5\u770B\u6AA2\u67E5\u7BC4\u570D \xB7 ${checked} \u5C64\u5DF2\u53D6\u5F97\u8CC7\u6599`;
    $("backend-status").textContent = result?.backend === "incompatible" ? "\u5F8C\u7AEF\u62D2\u7D55\u65B0\u7248\u8CC7\u6599\u683C\u5F0F\u3002\u8ACB\u91CD\u555F Python \u5F8C\u7AEF\uFF0C\u4E26\u91CD\u65B0\u8F09\u5165\u64F4\u5145\u529F\u80FD\u3002" : result?.backend === "rate_limited" ? "\u5F8C\u7AEF\u67E5\u8A62\u983B\u7387\u5DF2\u9054\u4E0A\u9650\uFF0C\u8ACB\u7A0D\u5019\u4E00\u5206\u9418\u3002\u672C\u6A5F\u6AA2\u67E5\u4ECD\u6709\u6548\u3002" : result?.backend === "unavailable" ? "\u672C\u6A5F\u9632\u8B77\u6301\u7E8C\u904B\u4F5C\u3002\u5F8C\u7AEF\u672A\u9023\u7DDA\uFF0C\u9032\u968E\u5206\u6790\u66AB\u4E0D\u53EF\u7528\u3002" : result?.backend === "pairing_required" ? "\u5F8C\u7AEF\u914D\u5C0D\u78BC\u4E0D\u6B63\u78BA\uFF0C\u8ACB\u81F3\u8A2D\u5B9A\u91CD\u65B0\u9023\u7DDA\u3002" : result?.backend === "checking" ? "\u672C\u6A5F\u6AA2\u67E5\u5B8C\u6210\uFF0C\u5F8C\u7AEF\u6B63\u5728\u88DC\u5145\u5206\u6790\u2026" : result?.source === "backend" ? "\u5DF2\u6574\u5408\u5F8C\u7AEF\u5206\u6790\uFF1B\u672A\u53D6\u5F97\u8CC7\u6599\u7684\u5C64\u4ECD\u6703\u6A19\u793A\u3002" : "\u672C\u6A5F\u5075\u6E2C\u6301\u7E8C\u904B\u4F5C\uFF1B\u53EF\u5728\u8A2D\u5B9A\u9023\u63A5\u9032\u968E\u5206\u6790\u3002";
    $("rescan").disabled = !supported || !enabled;
  }
  async function init() {
    try {
      const data = await send({ type: "GET_STATE" });
      if (data.error) throw Error();
      coverageOptions = data;
      activeTabId = data.tabId;
      render(data.state, data.supported, data.enabled);
      $("list-info").textContent = data.listCount ? `${data.listCount.toLocaleString()} \u7B46\u532F\u5165\u540D\u55AE \xB7 \u975E\u5373\u6642\u66F4\u65B0` : "\u540D\u55AE\u8F09\u5165\u5931\u6557 \xB7 \u8ACB\u91CD\u65B0\u8F09\u5165\u64F4\u5145\u529F\u80FD";
    } catch {
      $("headline").textContent = "\u66AB\u6642\u7121\u6CD5\u9023\u63A5\u96F7\u9054";
      $("description").textContent = "\u8ACB\u91CD\u65B0\u958B\u555F\u9019\u500B\u9762\u677F\u6216\u91CD\u65B0\u8F09\u5165\u64F4\u5145\u529F\u80FD\u3002";
    }
  }
  $("settings").onclick = () => chrome.runtime.openOptionsPage();
  $("enabled").onchange = async () => {
    await send({
      type: "SAVE_SETTINGS",
      settings: { enabled: $("enabled").checked }
    });
    await init();
  };
  for (const name of ["overview", "manual"])
    $(name + "-tab").onclick = () => {
      for (const tab of ["overview", "manual"]) {
        $(tab).hidden = tab !== name;
        $(tab + "-tab").setAttribute("aria-selected", String(tab === name));
      }
      if (name === "manual") $("url").focus();
    };
  $("rescan").onclick = async () => {
    $("rescan").disabled = true;
    $("backend-status").textContent = "\u6B63\u5728\u91CD\u65B0\u6AA2\u67E5\u2026";
    await send({ type: "CHECK_SITE", source: "current" }).catch(() => null);
    await init();
  };
  $("screenshot").onclick = async () => {
    if (!confirm(
      "\u5C07\u622A\u53D6\u76EE\u524D\u5206\u9801\u7684\u53EF\u898B\u756B\u9762\u4E26\u50B3\u5230\u672C\u6A5F\u5F8C\u7AEF\uFF1B\u5F8C\u7AEF\u6703\u4F9D\u8A2D\u5B9A\u50B3\u7D66 AI \u5206\u6790\u3002\u756B\u9762\u53EF\u80FD\u542B\u6709\u654F\u611F\u8CC7\u6599\u3002\u8981\u7E7C\u7E8C\u55CE\uFF1F"
    ))
      return;
    $("screenshot").disabled = true;
    $("backend-status").textContent = "\u6B63\u5728\u622A\u53D6\u756B\u9762\u4E26\u8ACB AI \u5206\u6790\u2026";
    try {
      const data = await send({ type: "ANALYZE_SCREENSHOT" });
      if (data.error) throw Error(data.error);
      $("backend-status").textContent = data.vision === "ok" ? "\u622A\u5716\u5206\u6790\u5B8C\u6210\u3002" : "\u622A\u5716\u5DF2\u9001\u5230\u5F8C\u7AEF\uFF0C\u4F46 AI \u5206\u6790\u672A\u57F7\u884C\uFF1B\u8ACB\u78BA\u8A8D\u5F8C\u7AEF\u7684 LLM \u8207\u5167\u5BB9\u4E0A\u50B3\u8A2D\u5B9A\u3002";
      await init();
    } catch (error) {
      const messages = {
        BACKEND_DISABLED: "\u8ACB\u5148\u5728\u8A2D\u5B9A\u9023\u63A5\u672C\u6A5F\u5F8C\u7AEF\u4E26\u5B8C\u6210\u914D\u5C0D\u3002",
        LLM_DISABLED: "\u8ACB\u5148\u5728\u8A2D\u5B9A\u958B\u555F AI \u8F14\u52A9\u5BE9\u67E5\u3002",
        PROTECTION_DISABLED: "\u8ACB\u5148\u958B\u555F\u9632\u8B77\u529F\u80FD\u3002",
        PAGE_NOT_READY: "\u9801\u9762\u8CC7\u6599\u5C1A\u672A\u6E96\u5099\u597D\uFF0C\u8ACB\u7A0D\u5F8C\u518D\u8A66\u3002",
        SCREENSHOT_TOO_LARGE: "\u622A\u5716\u8D85\u904E 5 MB\uFF0C\u7121\u6CD5\u4E0A\u50B3\u3002"
      };
      $("backend-status").textContent = messages[error.message] || "\u622A\u5716\u5206\u6790\u5931\u6557\uFF0C\u8ACB\u78BA\u8A8D\u672C\u6A5F\u5F8C\u7AEF\u6B63\u5728\u57F7\u884C\u3002";
    } finally {
      $("screenshot").disabled = false;
    }
  };
  $("scan-form").onsubmit = async (e) => {
    e.preventDefault();
    $("scan").disabled = true;
    $("manual-status").textContent = "\u6B63\u5728\u6AA2\u67E5\u2026";
    $("manual-result").replaceChildren();
    try {
      const data = await send({
        type: "CHECK_SITE",
        source: "manual",
        url: $("url").value.trim()
      });
      if (data.error) throw Error(data.error);
      const heading = document.createElement("strong");
      const score = data.result.decision.risk_score;
      heading.textContent = score >= 80 ? "\u5EFA\u8B70\u505C\u6B62\u524D\u5F80\u6B64\u7DB2\u5740" : score > 0 ? "\u6709\u9700\u67E5\u8B49\u7684\u98A8\u96AA\u8A0A\u865F" : "\u76EE\u524D\u672A\u547D\u4E2D\u5DF2\u57F7\u884C\u7684\u898F\u5247";
      $("manual-result").append(heading);
      for (const reason of data.result.decision.reasons) {
        const p = document.createElement("p");
        p.textContent = reason;
        $("manual-result").append(p);
      }
      const line = document.createElement("p");
      line.textContent = data.finalUrl ? `HTTP \u843D\u5730\u9801\uFF1A${data.finalUrl}` : data.url;
      $("manual-result").append(line);
      $("manual-status").textContent = data.fetchStatus === "http_only_no_javascript" ? "\u5DF2\u6AA2\u67E5 HTTP \u8F49\u5740\u8207\u975C\u614B\u5167\u5BB9\uFF1B\u672A\u57F7\u884C JavaScript\u3002" : "\u672C\u6A5F\u7DB2\u5740\u6AA2\u67E5\u5B8C\u6210\uFF1B\u672A\u53D6\u5F97\u843D\u5730\u9801\u5167\u5BB9\uFF0C\u4E0D\u4EE3\u8868\u7DB2\u7AD9\u5B89\u5168\u3002";
    } catch {
      $("manual-status").textContent = "\u7121\u6CD5\u6AA2\u67E5\uFF0C\u8ACB\u8F38\u5165\u5B8C\u6574\u7684 http:// \u6216 https:// \u7DB2\u5740\u3002";
    } finally {
      $("scan").disabled = false;
    }
  };
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "session" && changes[`tab:${activeTabId}`]?.newValue)
      render(changes[`tab:${activeTabId}`].newValue, true, $("enabled").checked);
  });
  void init();
})();

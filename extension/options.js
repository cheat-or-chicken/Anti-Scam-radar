(() => {
  // src/options.js
  var $ = (id) => document.getElementById(id);
  var send = (message) => chrome.runtime.sendMessage(message);
  function values() {
    return {
      enabled: $("enabled").checked,
      backendEnabled: $("backendEnabled").checked,
      screenshotEnabled: $("screenshotEnabled").checked,
      llmEnabled: $("llmEnabled").checked,
      pairingToken: $("pairingToken").value.trim()
    };
  }
  async function save() {
    const r = await send({ type: "SAVE_SETTINGS", settings: values() });
    if (r.error) throw Error(r.error);
  }
  $("options-form").onsubmit = async (e) => {
    e.preventDefault();
    try {
      await save();
      $("status").textContent = "\u8A2D\u5B9A\u5DF2\u5132\u5B58\uFF0C\u6703\u5957\u7528\u81F3\u76EE\u524D\u5206\u9801\u3002";
    } catch (e2) {
      $("status").textContent = e2.message === "USE_PAIRING_TOKEN" ? "\u8ACB\u8CBC\u4E0A\u672C\u6A5F\u914D\u5C0D\u78BC\uFF0C\u4E0D\u8981\u5C07 OpenAI API key \u653E\u5165\u64F4\u5145\u529F\u80FD\u3002" : "\u5132\u5B58\u5931\u6557\uFF0C\u8ACB\u91CD\u65B0\u958B\u555F\u8A2D\u5B9A\u3002";
    }
  };
  $("test").onclick = async () => {
    $("test").disabled = true;
    $("status").textContent = "\u6B63\u5728\u78BA\u8A8D\u5F8C\u7AEF\u9023\u7DDA\u8207\u914D\u5C0D\u2026";
    try {
      await save();
      const r = await send({ type: "PING_BACKEND" });
      if (r.error) throw Error(r.error);
      $("status").textContent = "\u9023\u7DDA\u6210\u529F\uFF01\u914D\u5C0D\u5DF2\u78BA\u8A8D\uFF0C\u672C\u6A5F\u5206\u6790\u670D\u52D9\u53EF\u7528\u3002";
    } catch (e) {
      $("status").textContent = e.message === "PAIRING_REQUIRED" ? "\u914D\u5C0D\u78BC\u4E0D\u6B63\u78BA\uFF0C\u8ACB\u91CD\u65B0\u8907\u88FD extension-token.txt\u3002" : "\u5C1A\u672A\u9023\u7DDA\u3002\u8ACB\u555F\u52D5\u672C\u6A5F\u5F8C\u7AEF\uFF0C\u4E26\u78BA\u8A8D\u914D\u5C0D\u78BC\u3002";
    } finally {
      $("test").disabled = false;
    }
  };
  send({ type: "GET_SETTINGS" }).then((options) => {
    for (const field of ["enabled", "backendEnabled", "llmEnabled", "screenshotEnabled"])
      $(field).checked = options[field] === true;
    $("pairingToken").value = options.pairingToken || "";
  }).catch(() => {
    $("status").textContent = "\u8B80\u53D6\u8A2D\u5B9A\u5931\u6557\u3002";
  });
})();

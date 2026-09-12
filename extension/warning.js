(() => {
  // src/warning_state.js
  function warningReasons(result) {
    return [...new Set([
      ...result?.decision?.reasons || [],
      ...(result?.layers || []).flatMap((layer) => (layer.signals || []).filter((signal) => signal.weight > 0).map((signal) => signal.detail))
    ].filter((text) => typeof text === "string" && text.trim()))];
  }

  // src/warning.js
  var send = (type) => chrome.runtime.sendMessage({ type });
  var $ = (id) => document.getElementById(id);
  send("GET_WARNING").then((data) => {
    if (data.error) throw Error();
    const url = new URL(data.originalUrl);
    $("originalUrl").textContent = url.origin + url.pathname;
    for (const reason of warningReasons(data.result)) {
      const li = document.createElement("li");
      li.textContent = reason;
      $("reasons").append(li);
    }
    $("proceedBtn").disabled = false;
  }).catch(() => {
    $("status").textContent = "\u9019\u4EFD\u63D0\u9192\u5DF2\u904E\u671F\uFF0C\u8ACB\u95DC\u9589\u5206\u9801\u5F8C\u91CD\u65B0\u78BA\u8A8D\u7DB2\u5740\u3002";
  });
  $("leaveBtn").onclick = async () => {
    const r = await send("LEAVE_DANGEROUS_SITE");
    if (r.error) window.close();
  };
  $("proceedBtn").onclick = async () => {
    $("proceedBtn").disabled = true;
    const r = await send("PROCEED_ANYWAY");
    if (r.error) {
      $("status").textContent = "\u653E\u884C\u5931\u6557\uFF0C\u8ACB\u91CD\u65B0\u78BA\u8A8D\u7DB2\u5740\u3002";
      $("proceedBtn").disabled = false;
    }
  };
})();

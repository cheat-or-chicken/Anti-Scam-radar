const $ = (id) => document.getElementById(id);
const send = (message) => chrome.runtime.sendMessage(message);
function values() {
  return {
    enabled: $("enabled").checked,
    backendEnabled: $("backendEnabled").checked,
    llmEnabled: $("llmEnabled").checked,
    pairingToken: $("pairingToken").value.trim(),
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
    $("status").textContent = "設定已儲存，會套用至目前分頁。";
  } catch (e) {
    $("status").textContent =
      e.message === "USE_PAIRING_TOKEN"
        ? "請貼上本機配對碼，不要將 OpenAI API key 放入擴充功能。"
        : "儲存失敗，請重新開啟設定。";
  }
};
$("test").onclick = async () => {
  $("test").disabled = true;
  $("status").textContent = "正在確認後端連線與配對…";
  try {
    await save();
    const r = await send({ type: "PING_BACKEND" });
    if (r.error) throw Error(r.error);
    $("status").textContent = "連線成功！配對已確認，本機分析服務可用。";
  } catch (e) {
    $("status").textContent =
      e.message === "PAIRING_REQUIRED"
        ? "配對碼不正確，請重新複製 extension-token.txt。"
        : "尚未連線。請啟動本機後端，並確認配對碼。";
  } finally {
    $("test").disabled = false;
  }
};
send({ type: "GET_SETTINGS" })
  .then((options) => {
    for (const field of ["enabled", "backendEnabled", "llmEnabled"])
      $(field).checked = options[field] === true;
    $("pairingToken").value = options.pairingToken || "";
  })
  .catch(() => {
    $("status").textContent = "讀取設定失敗。";
  });

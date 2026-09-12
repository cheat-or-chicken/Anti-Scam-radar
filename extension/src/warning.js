const send = (type) => chrome.runtime.sendMessage({ type });
const $ = (id) => document.getElementById(id);
send("GET_WARNING")
  .then((data) => {
    if (data.error) throw Error();
    const url = new URL(data.originalUrl);
    $("originalUrl").textContent = url.origin + url.pathname;
    for (const reason of data.result.decision.reasons) {
      const li = document.createElement("li");
      li.textContent = reason;
      $("reasons").append(li);
    }
    $("proceedBtn").disabled = false;
  })
  .catch(() => {
    $("status").textContent = "這份提醒已過期，請關閉分頁後重新確認網址。";
  });
$("leaveBtn").onclick = async () => {
  const r = await send("LEAVE_DANGEROUS_SITE");
  if (r.error) window.close();
};
$("proceedBtn").onclick = async () => {
  $("proceedBtn").disabled = true;
  const r = await send("PROCEED_ANYWAY");
  if (r.error) {
    $("status").textContent = "放行失敗，請重新確認網址。";
    $("proceedBtn").disabled = false;
  }
};

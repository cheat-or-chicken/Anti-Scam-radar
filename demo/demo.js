// Demo only: never read input values, send requests, store data, or download software.
document.addEventListener('submit', event => {
  event.preventDefault();
  document.querySelector('.status').textContent = '演示到此結束。沒有傳送任何資料。';
});
document.querySelectorAll('[data-simulate]').forEach(button => button.addEventListener('click', () => {
  document.querySelector('.status').textContent = '僅顯示模擬步驟。沒有下載或安裝程式。';
}));
document.querySelector('#reveal')?.addEventListener('click', event => {
  event.currentTarget.disabled = true;
  event.currentTarget.textContent = '領取資格已確認';
  const panel = document.querySelector('#claim-panel');
  const message = document.createElement('div');
  message.className = 'notice';
  message.textContent = '提供 OTP 驗證碼給客服，即可完成獎金領取。';
  const label = document.createElement('label');
  label.htmlFor = 'late-otp';
  label.textContent = '簡訊驗證碼';
  const input = document.createElement('input');
  input.id = 'late-otp'; input.name = 'otp'; input.autocomplete = 'one-time-code';
  input.placeholder = '僅用 000000 演示'; input.maxLength = 6;
  panel.append(message, label, input);
  document.querySelector('.status').textContent = '新表單已出現，等候擴充功能重新檢查約 5 秒。';
});

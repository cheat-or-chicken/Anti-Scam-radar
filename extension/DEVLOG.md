# 防詐雷達開發日誌

**專案**：anti-fraud-radar　**日期**：2026-09-09　**平台**：Chrome Extension · Manifest V3

今天把「背景靜默探路」從一支會噴例外的草稿，磨成通過 27 項自動化測試、能即時比對 3.2 萬筆政府詐騙網址的擴充功能。這篇記錄用到的技術棧，跟一路踩過、修掉的每一個 bug。

**8** 個修掉的 bug　**27** 項通過的測試　**32,642** 筆黑名單網域　**10s** 硬性逾時上限

---

## 今天用到的技術

### Chrome Extension · Manifest V3
- `chrome.windows` — 建立/銷毀最小化隱形視窗
- `chrome.tabs` — update(muted) / onRemoved / query
- `chrome.scripting` — executeScript 動態注入擷取
- `chrome.webNavigation` — onCompleted / onCommitted
- `chrome.webRequest` — onBeforeRedirect
- `chrome.downloads` — onDeterminingFilename 攔截
- `chrome.runtime` — onMessage 橋接 / getURL
- `host_permissions: <all_urls>`

### 資料工程
- CSV 解析（NPA_WEBURL.csv，45,259 列）
- JSON 合併去重（TWNIC，1,612 筆）
- Set 型別 O(1) 精確 / 子網域比對
- 數字骨架正規化索引（相似網域偵測）

### 測試方法論
- Node `vm` 模組 mock 整套 chrome.* API
- 本機 Node http 伺服器當即時測試夾具
- 無真實瀏覽器的邏輯層迴歸測試

---

## 踩過的 8 個 bug

### #01 tabs.create() 不吃 muted 屬性 `阻斷`

- **症狀**：Service worker console 噴出 `Unexpected property: 'muted'`，`scanUrl()` 從一開始就整支失敗。
- **原因**：`muted` 只存在於 `tabs.update()` 的 updateProperties，`tabs.create()` 的 createProperties 根本沒有這個欄位。
- **修法**：分成兩步：先 create 分頁，拿到 tabId 後再額外呼叫一次 `tabs.update(tabId, {muted:true})`。

### #02 active:false 不等於「使用者看不到」 `設計缺陷`

- **症狀**：實測時分頁還是會在分頁列上閃一下，跟「背景靜默探路」的規格不符。
- **原因**：`active:false` 只代表「不搶走目前分頁的焦點」，分頁本身仍會出現在使用者當下視窗的分頁列。
- **修法**：改用 `chrome.windows.create({focused:false, state:'minimized'})`，探路分頁開在一個獨立的最小化視窗裡。

### #03 redirected 判定邏輯錯誤 `邏輯`

- **症狀**：完全沒轉址的網頁也回報 `redirected:true`。
- **原因**：把「任何一次 `onCompleted`」都當成跳轉的證據——但第一次 onCompleted 其實只是初始頁面本身載入完成。
- **修法**：改成 `onCompleted` 觸發超過一次（代表初始頁面之後又有新導航）或 `onBeforeRedirect` 真的觸發過，兩者任一成立才算跳轉。

### #04 安靜期太短，搶先擷取到過渡頁 `邏輯`

- **症狀**：本機測試頁面用 `setTimeout(1500ms)` 做 JS 轉址，結果 `finalUrl` 抓到的還是轉址前的「loading...」畫面。
- **原因**：`NAV_QUIET_MS` 只有 1200ms，比實際轉址延遲短，擷取腳本在真正跳轉發生「之前」就先執行了。
- **修法**：安靜期拉長到 3000ms；同時記下這仍是機率性折衷，超過安靜期的刻意延遲轉址交給 10 秒硬性 Timeout 兜底。

### #05 onBeforeRedirect 掛錯 API 命名空間 `阻斷`

- **症狀**：`Cannot read properties of undefined (reading 'addListener')`，整條 scanUrl 流程靜默卡死。
- **原因**：把 `onBeforeRedirect` 掛在 `chrome.webNavigation` 下面——這個事件其實屬於 `chrome.webRequest`，命名空間記錯了。
- **修法**：改成 `chrome.webRequest.onBeforeRedirect.addListener(fn, {urls:['<all_urls>']})`，manifest 補上 `webRequest` 權限。

### #06 vm 模組的 const/let 不會掛到 sandbox `測試基礎設施`

- **症狀**：明明黑名單資料是對的，mock 測試卻回報比對失敗。
- **原因**：Node `vm` 模組頂層用 const/let 宣告的變數不會變成 sandbox 物件的屬性（只有 function 宣告和 var 會），`await sandbox.blocklistReady` 等於在等一個 undefined，沒真的等到非同步載入跑完。
- **修法**：測試裡改成等一小段真實時間，讓背景腳本內部真正的 fetch().then() 鏈跑完，而不是依賴從外部存取那個變數。

### #07 純數字網域讓相似度索引太籠統 `資料品質`

- **症狀**：檢查產出的索引時發現 `www.1672211.com` 這類網域，換算成骨架後變成 `www.#.com`——任何無關的純數字 .com 網域都會被誤判成「高度相似」。
- **原因**：數字骨架比對是把數字都換成 `#`；當某一段本身整段都是數字，換完就只剩一個毫無辨識度的萬用符號。
- **修法**：建索引前先排除「任一段整段都是數字」的網域，527 組骨架索引降到 487 組更乾淨的版本。

### #08 新增全域監聽器後，舊測試抓錯監聽器 `測試基礎設施`

- **症狀**：加了即時瀏覽監控後，一個原本綠燈的舊測試突然回報 `redirected:false`。
- **原因**：即時監控在模組載入時就註冊了一個全域的 `onBeforeRedirect` 監聽器；舊測試寫死 `listeners[0]`，現在抓到的是那個全域監聽器，不是 `scanUrl()` 這次呼叫自己註冊的那個。
- **修法**：改成抓陣列最後一個（最新註冊的）監聽器，而不是假設 index 固定是 0。

---

anti-fraud-radar / 防詐雷達　·　2026-09-09

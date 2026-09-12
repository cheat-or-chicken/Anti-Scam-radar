# AI 證據整合工作流

預設擴充功能仍執行固定適用檢查，最後增加一次 LLM 情境整合，不讓規劃器自行略過檢查。原 CLI deep 模式仍屬額外調查。此版沒有週期排程或自動改寫規則。

## 四個部分

- `script/workflow.py`：辨識網站可能目的、比較詐騙／正常／資料不足假設、引用支持與反對證據、指出未知與改判條件。`assess` 使用既有 LLM 共用預算和結構化輸出；引用不存在或格式失敗，回退原本裁決。
- 同檔 `apply_assessment`：記錄模型建議與實際接受動作；不降低既有分數、不重複加總既有證據。模型單獨不能封鎖網站；暫停敏感操作需引用目前的實質風險訊號，歷史／頁面宣稱不能單獨觸發。
- `extension/src/journey.js`：每個分頁在 session 保存最多 8 個去重摘要，15 分鐘無活動失效，關分頁清除。包含訊號 ID、敏感欄位數與網域是否變更；沒有完整 URL、文字、輸入值或截圖。歷史是未驗證的上下文，不是已付款或外傳的證據。
- 同檔 `diagnose` 與後端 `/v1/diagnose`：以既有 audit_id 和人工確認的 scam/legitimate 標籤診斷採集、理解、權重或介入時機問題，回傳候選修正與正常反例；不自動套用。需原本 Bearer 配對，JSON 包含 audit_id、confirmed_label、reviewed:true。此 API 尚未提供獨立審核 UI；reviewed 是呼叫者的人工確認聲明，不是外部事實驗證。

`script/pipeline.py` 將報告放進 workflow，摘要放 WORKFLOW 層；`extension/src/core.js` 保留其結果與接受的介入，popup 檢查範圍可查看假設與待查證事項。`script/models.py` 定義跨頁輸入界限。原文只在呼叫期間提供，返回／稽核不保存頁面證據原文；生成摘要仍可能含頁面資訊，不適合當作已完全去識別資料。

## 預算與限制

`workflow_enabled` 預設 true，可設 false 做同版本 A/B 比較。整合共用 max_llm_calls；足夠預算時預留一次，只有一次預算時仍優先 L7，額度不足顯示跳過。固定本機規則不因模型額度而停止；六項 LLM 補充依現有固定優先序受額度限制。

證據 ID 檢查只能驗證引用存在，不能保證語意推論正確。正式效果需用人工標記、獨立保留案例比較誤報／漏報、延遲與成本，不能以單元測試數量宣稱準確率提升。

## 驗證

Python 測試涵蓋虛構引用拒絕、原文不返回、歷史不能單獨阻擋、禁止降低既有封鎖、離線與診斷候選。Node 測試涵蓋跨頁去重／到期／數量上限與零分情境提醒合併。

結構化輸出採既有 Responses API wrapper，參考 [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)。L7 仍不執行 JS。

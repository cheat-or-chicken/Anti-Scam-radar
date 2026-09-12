# 專案維護方式

## CI 與檢查範圍

GitHub Actions 的 `.github/workflows/checks.yml` 在 push 與 pull request 時執行。Python 使用 uv.lock、Python 3.12 與 dev extra，前端使用 Node 22 與 package-lock.json。

1. Ruff 靜態檢查與格式驗證，包含 script、tests、ChatRoom（含 RAG 工具）。
2. pytest 單元／整合測試與 script.evaluate 合成案例回歸。
3. Node 原生測試、esbuild 建置，確認產物與 Git 已提交版本一致。
4. Playwright 啟動 Chromium 與本機聊天室，用模擬 API 驗證網址卡片、警告暫停與手動繼續。

本次本機驗證為 228 項 Python 測試、26 項 Node 測試，另有聊天室瀏覽器回歸及 30 個合成評估案例。這些數字代表測試範圍，不是真實詐騙偵測準確率。CI 不需要正式 LLM／Google key；RAG 的 Ollama／PDF 索引與真實外部 API 效果不包含在這組 CI 端到端測試中。

## 協作與專案管理

目前可確認使用 Git／GitHub 分支、commit、Pull Request 與 Markdown 文件。每項修改在分支開發，PR 保留差異與討論，Actions 保留檢查結果。沒有據此宣稱已使用 Jira、Trello 或 GitHub Projects，也沒有假設 main 已設定強制通過檢查的保護規則。使用 fixtures、tests 與 docs 記錄案例、回歸及操作流程。

## 本機建置與部署

```bash
uv sync --locked --python 3.12 --extra dev
npm ci --prefix extension
npm run build --prefix extension
uv run python -m script.server
```

在另一個終端啟動聊天室：

```bash
uv run python -m ChatRoom.server
```

網站 API 在 127.0.0.1:8765，聊天室在 127.0.0.1:8000。Chrome 載入 extension 資料夾，或先用 `uv run python -m script.package_extension` 封裝再分發。更新後手動重啟後端、重新載入擴充功能並重新整理頁面。目前不是雲端自動部署，也沒有 Web Store 自動發布。

本機 key 放 config/config.local.json 或對應環境設定，Git 忽略秘密值。後端進度可查 var/backend.log，分析稽核與對話紀錄供人工追查；未知／失敗不能當作安全。回復版本時先保存本機修改，再由維護者選擇已確認 commit 重新建置部署。

## 本次 CI 修正

- 同步 main 的 00968bf RAG 模擬對話新增內容。
- 修正 RAG imports 並依鎖定 Ruff 統一 Python 格式。
- pytest 設定加入 repo pythonpath，修正 pytest 啟動時無法 import ChatRoom；CI 使用 python -m pytest。
- 將既有 Node、extension 建置一致性、聊天室 Playwright 回歸加入 Actions。
